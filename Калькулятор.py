from __future__ import annotations

import ast
import importlib
import math
import random
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple, Union

import tkinter as tk
from tkinter import messagebox

try:
    import customtkinter as ctk
except Exception as exc:
    raise ImportError("Пакет 'customtkinter' не найден. Установите: python -m pip install customtkinter") from exc

DEPENDENCIES: List[Tuple[str, str]] = [
    ("pytweening", "pytweening"),
    ("easing-functions", "easing_functions"),
    ("numpy", "numpy"),
]

def _in_venv() -> bool:
    return (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix) or hasattr(sys, "real_prefix")

def _try_import_module(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None

def _run_pip_install_noninteractive(pip_name: str, use_user: bool) -> Tuple[bool, str, str]:
    cmd = [sys.executable, "-m", "pip", "install", pip_name]
    if use_user:
        cmd.append("--user")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return (proc.returncode == 0, proc.stdout or "", proc.stderr or "")
    except Exception as exc:
        return (False, "", str(exc))

def install_package_with_gui(root: tk.Tk, pkg: str, use_user: bool) -> Tuple[bool, str, str]:
    """
    GUI installer: runs pip in background and shows a Toplevel window with live output.
    """
    res = {"rc": 1, "out": "", "err": "", "done": False}
    cancelled = {"flag": False}

    win = tk.Toplevel(root)
    win.title(f"Установка {pkg}")
    win.geometry("640x320")
    win.transient(root)
    tk.Label(win, text=f"Устанавливается пакет: {pkg}", anchor="w").pack(fill="x", padx=8, pady=(8, 0))
    txt = tk.Text(win, wrap="word", height=14)
    txt.pack(fill="both", expand=True, padx=8, pady=8)
    txt.configure(state="disabled")

    btn_frame = tk.Frame(win)
    btn_frame.pack(fill="x", padx=8, pady=(0, 8))
    progress_var = tk.StringVar(value="Запуск установки...")
    lbl = tk.Label(btn_frame, textvariable=progress_var)
    lbl.pack(side="left")

    def on_cancel():
        if messagebox.askyesno("Отмена", "Прервать установку?", parent=win):
            cancelled["flag"] = True
            progress_var.set("Отмена...")

    tk.Button(btn_frame, text="Прервать", command=on_cancel).pack(side="right")

    def append_line(line: str):
        txt.configure(state="normal")
        txt.insert("end", line)
        txt.see("end")
        txt.configure(state="disabled")

    def run_install():
        cmd = [sys.executable, "-m", "pip", "install", pkg]
        if use_user:
            cmd.append("--user")
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        except Exception as exc:
            res["out"] = ""
            res["err"] = str(exc)
            res["rc"] = 1
            res["done"] = True
            try:
                root.after(10, win.destroy)
            except Exception:
                pass
            return

        out_accum = ""
        try:
            while True:
                if cancelled["flag"]:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    res["out"] = out_accum
                    res["err"] = "Отменено пользователем"
                    res["rc"] = 1
                    res["done"] = True
                    try:
                        root.after(10, win.destroy)
                    except Exception:
                        pass
                    return
                line = proc.stdout.readline()
                if line:
                    out_accum += line
                    try:
                        root.after(0, append_line, line)
                    except Exception:
                        pass
                if proc.poll() is not None:
                    rest = proc.stdout.read() or ""
                    if rest:
                        out_accum += rest
                        try:
                            root.after(0, append_line, rest)
                        except Exception:
                            pass
                    break
            res["out"] = out_accum
            res["err"] = ""
            res["rc"] = proc.returncode or 0
            res["done"] = True
        except Exception as exc:
            res["out"] = out_accum
            res["err"] = str(exc)
            res["rc"] = 1
            res["done"] = True
        finally:
            try:
                root.after(10, win.destroy)
            except Exception:
                pass

    t = threading.Thread(target=run_install, daemon=True)
    t.start()

    try:
        root.wait_window(win)
    except Exception:
        pass
    return (res["rc"] == 0), res["out"], res["err"]

def ensure_and_import_with_gui(pkgs: List[Tuple[str, str]]) -> Dict[str, Optional[object]]:
    headless = False
    root: Optional[tk.Tk] = None
    try:
        root = tk.Tk()
        root.withdraw()
    except Exception:
        headless = True
        root = None

    imported: Dict[str, Optional[object]] = {}

    for pip_name, module_name in pkgs:
        mod = _try_import_module(module_name)
        if mod:
            imported[module_name] = mod
            continue

        if headless:
            use_user = not _in_venv()
            success, out, err = _run_pip_install_noninteractive(pip_name, use_user)
            if success:
                mod = _try_import_module(module_name)
                imported[module_name] = mod
                continue
            else:
                imported[module_name] = None
                continue

        try:
            answer = messagebox.askyesno("Зависимость отсутствует",
                                         f"Пакет '{pip_name}' (модуль '{module_name}') не найден.\nУстановить сейчас? (рекомендовано для плавных анимаций)",
                                         parent=root)
        except Exception:
            answer = False
        if not answer:
            imported[module_name] = None
            continue

        while True:
            use_user = not _in_venv()
            success, out, err = install_package_with_gui(root, pip_name, use_user)
            if success:
                mod = _try_import_module(module_name)
                if mod:
                    imported[module_name] = mod
                    break
                else:
                    msg = f"Пакет '{pip_name}' был установлен, но импорт модуля '{module_name}' не удался.\n\nSTDOUT:\n{out}\n\nSTDERR:\n{err}"
                    try:
                        retry = messagebox.askretrycancel("Ошибка импорта", msg + "\n\nПовторить попытку импорта?", parent=root)
                    except Exception:
                        retry = False
                    if not retry:
                        imported[module_name] = None
                        break
            else:
                msg = f"Не удалось установить пакет '{pip_name}'.\n\nSTDOUT:\n{out}\n\nSTDERR:\n{err}"
                try:
                    choice = messagebox.askretrycancel("Ошибка установки", msg + "\n\nНажмите 'Повторить' чтобы попробовать снова, 'Отмена' чтобы пропустить.", parent=root)
                except Exception:
                    choice = False
                if choice:
                    continue
                else:
                    imported[module_name] = None
                    break

    if root is not None:
        try:
            root.destroy()
        except Exception:
            pass
    return imported

_imported_optional = ensure_and_import_with_gui(DEPENDENCIES)
_np = _imported_optional.get("numpy")
_pt = _imported_optional.get("pytweening")
_easing_mod = _imported_optional.get("easing_functions")

_BackEaseOut = None
if _easing_mod is not None:
    try:
        from easing_functions import BackEaseOut as _BackEaseOut  # type: ignore
    except Exception:
        _BackEaseOut = None
else:
    try:
        temp = _try_import_module("easing_functions")
        if temp is not None:
            try:
                from easing_functions import BackEaseOut as _BackEaseOut  # type: ignore
            except Exception:
                _BackEaseOut = None
    except Exception:
        _BackEaseOut = None

HAVE_NUMPY = _np is not None
HAVE_PYTWEEN = _pt is not None
HAVE_EASING_LIB = _BackEaseOut is not None

# ---------------------------
# Configuration
# ---------------------------
@dataclass(frozen=True)
class Config:
    appearance_mode: str = "dark"
    color_theme: str = "dark-blue"
    win_w: int = 300
    win_h: int = 420
    win_alpha: float = 0.97
    resizable: Tuple[bool, bool] = (False, False)
    entry_h: int = 38
    compact_entry_h: int = 28
    btn_h: int = 42
    btn_corner: int = 6
    container_pad: int = 8
    max_input: int = 64

    panel: str = "#0d1114"
    surface: str = "#0b0d10"
    card: str = "#0f1316"
    accent: str = "#2b5fa0"
    accent_alt: str = "#233240"
    text: str = "#e6eef8"
    muted: str = "#7e8a94"

    def fonts(self):
        try:
            return {
                "ui": ctk.CTkFont(size=13),
                "bold": ctk.CTkFont(size=14, weight="bold"),
                "small": ctk.CTkFont(size=12, weight="bold"),
            }
        except Exception:
            return {
                "ui": ("Helvetica", 13),
                "bold": ("Helvetica", 14, "bold"),
                "small": ("Helvetica", 12, "bold"),
            }

CFG = Config()
FONTS = CFG.fonts()

ctk.set_appearance_mode(CFG.appearance_mode)
try:
    ctk.set_default_color_theme(CFG.color_theme)
except Exception:
    pass

# ---------------------------
# Helpers: colors, numbers
# ---------------------------
def hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return 0, 0, 0

def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"

def adjust_brightness(hex_color: str, factor: float) -> str:
    try:
        r, g, b = hex_to_rgb(hex_color)
        r = max(0, min(255, int(r * factor)))
        g = max(0, min(255, int(g * factor)))
        b = max(0, min(255, int(b * factor)))
        return rgb_to_hex(r, g, b)
    except Exception:
        return hex_color

def hover_color(hex_color: str, factor: float = 0.06) -> str:
    try:
        r, g, b = hex_to_rgb(hex_color)
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        return rgb_to_hex(r, g, b)
    except Exception:
        return hex_color

def format_number(val: Union[int, float], decimals: int = 5, use_comma: bool = True) -> str:
    s = f"{float(val):.{decimals}f}"
    return s.replace(".", ",") if use_comma else s

def parse_number(s: str) -> Union[float, complex]:
    s = (s or "").strip()
    if not s:
        raise ValueError("Empty")
    if "j" in s or "J" in s:
        try:
            return complex(s.replace(",", "."))
        except Exception:
            raise ValueError("Invalid complex number")
    try:
        return float(s.replace(",", "."))
    except Exception:
        raise ValueError("Invalid float")

# ---------------------------
# Safe evaluation using AST
# ---------------------------
_ALLOWED_MATH = {k: getattr(math, k) for k in dir(math) if not k.startswith("__")}
_ALLOWED_EXTRA = {"abs": abs, "round": round, "min": min, "max": max}
_ALLOWED_NAMES = {**_ALLOWED_MATH, "pi": math.pi, "e": math.e, **_ALLOWED_EXTRA}

class _SafeEvalVisitor(ast.NodeVisitor):
    ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv)
    ALLOWED_UNARY = (ast.UAdd, ast.USub)
    def visit(self, node):
        nodetype = type(node)
        if nodetype in (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Constant,
                        ast.Load, ast.Tuple, ast.List, ast.Subscript, ast.Index, ast.Slice):
            return super().visit(node)
        if nodetype in (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv,
                        ast.UAdd, ast.USub):
            return
        raise ValueError(f"Недопустимый элемент выражения: {nodetype.__name__}")

    def visit_Expression(self, node: ast.Expression):
        self.visit(node.body)

    def visit_BinOp(self, node: ast.BinOp):
        if not isinstance(node.op, self.ALLOWED_BINOPS):
            raise ValueError("Оператор не разрешён")
        self.visit(node.left)
        self.visit(node.right)

    def visit_UnaryOp(self, node: ast.UnaryOp):
        if not isinstance(node.op, self.ALLOWED_UNARY):
            raise ValueError("Унарный оператор не разрешён")
        self.visit(node.operand)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name not in _ALLOWED_NAMES:
                raise ValueError(f"Функция '{func_name}' не разрешена")
        else:
            raise ValueError("Разрешены только прямые вызовы разрешённых функций")
        for a in node.args:
            self.visit(a)
        if node.keywords:
            raise ValueError("Ключевые аргументы не разрешены")

    def visit_Name(self, node: ast.Name):
        if node.id not in _ALLOWED_NAMES:
            raise ValueError(f"Имя '{node.id}' не разрешено")

    def visit_Constant(self, node: ast.Constant):
        if not isinstance(node.value, (int, float, complex)):
            raise ValueError("Разрешены только числовые константы")

    def visit_Tuple(self, node: ast.Tuple):
        for elt in node.elts:
            self.visit(elt)

    def visit_List(self, node: ast.List):
        for elt in node.elts:
            self.visit(elt)

def safe_eval(expr: str):
    """
    Safely evaluate a math expression using AST validation.
    """
    if not expr or not isinstance(expr, str):
        raise ValueError("Пустое выражение")
    src = expr.replace("^", "**").replace("×", "*").replace("÷", "/").replace(",", ".").strip()
    if "_" in src:
        raise ValueError("Символ '_' запрещён в выражениях")
    try:
        node = ast.parse(src, mode="eval")
        _SafeEvalVisitor().visit(node)
        code = compile(node, "<safe>", "eval")
        return eval(code, {"__builtins__": None}, _ALLOWED_NAMES)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Неверное выражение") from exc

# ---------------------------
# Animator
# ---------------------------
class Animator:
    def __init__(self, root: tk.Tk | tk.Toplevel):
        self.root = root
        self._jobs: Dict[str, int] = {}

    def cancel(self, name: str):
        job = self._jobs.pop(name, None)
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass

    def schedule(self, name: str, delay_ms: int, fn: Callable[[], None]):
        self.cancel(name)
        try:
            self._jobs[name] = self.root.after(delay_ms, fn)
        except Exception:
            def _delayed():
                try:
                    threading.Event().wait(delay_ms / 1000.0)
                    fn()
                except Exception:
                    pass
            t = threading.Thread(target=_delayed, daemon=True)
            t.start()

    def fade_in(self, win: tk.Toplevel | tk.Tk, target_alpha: float = 1.0, duration: int = 220, steps: int = 12):
        try:
            win.attributes("-alpha", 0.0)
        except Exception:
            try:
                win.wm_attributes("-alpha", 0.0)
            except Exception:
                return
        step_ms = max(1, duration // steps)

        def step(i: int = 0):
            a = (i + 1) / steps * target_alpha
            try:
                win.attributes("-alpha", a)
            except Exception:
                try:
                    win.wm_attributes("-alpha", a)
                except Exception:
                    return
            if i + 1 < steps:
                self.schedule(f"fade_{id(win)}", step_ms, lambda: step(i + 1))

        step(0)

    @staticmethod
    def _ease_out_cubic(t: float) -> float:
        return 1 - (1 - t) ** 3

    @staticmethod
    def _ease_out_back(t: float, s: float = 1.3) -> float:
        t -= 1
        return 1 + t * t * ((s + 1) * t + s)

    def _compute_factors(self, total_frames: int, shrink_factor: float, overshoot: float):
        down_ratio = 0.35
        up_ratio = 0.45
        down_frames = max(2, int(total_frames * down_ratio))
        up_frames = max(2, int(total_frames * up_ratio))
        settle_frames = max(1, total_frames - down_frames - up_frames)

        factors: List[float] = []

        if HAVE_NUMPY:
            import numpy as np  # type: ignore
            t_down = np.linspace(0.0, 1.0, down_frames, endpoint=True)
            t_up = np.linspace(0.0, 1.0, up_frames, endpoint=True)
            t_settle = np.linspace(0.0, 1.0, settle_frames, endpoint=True)

            def ease_array(name: str, arr):
                vals = []
                if HAVE_PYTWEEN and hasattr(_pt, name):
                    fn = getattr(_pt, name)
                    for x in arr:
                        vals.append(float(fn(float(x))))
                    return np.array(vals)
                if HAVE_EASING_LIB and name == "ease_out_back":
                    try:
                        for x in arr:
                            inst = _BackEaseOut(start=0, end=1, duration=1)  # type: ignore
                            vals.append(float(inst.ease(float(x))))
                        return np.array(vals)
                    except Exception:
                        pass
                if name == "ease_out_cubic":
                    return np.array([self._ease_out_cubic(float(x)) for x in arr])
                return np.array([self._ease_out_back(float(x), s=1.2) for x in arr])

            v_down = ease_array("easeOutCubic" if HAVE_PYTWEEN else "ease_out_cubic", t_down)
            factors.extend((1.0 + (shrink_factor - 1.0) * v_down).tolist())

            v_up = ease_array("easeOutCubic" if HAVE_PYTWEEN else "ease_out_cubic", t_up)
            factors.extend((shrink_factor + (overshoot - shrink_factor) * v_up).tolist())

            v_settle = ease_array("easeOutBack" if HAVE_PYTWEEN else "ease_out_back", t_settle)
            factors.extend((overshoot + (1.0 - overshoot) * v_settle).tolist())

            if factors:
                factors[-1] = 1.0
            return factors

        for i in range(down_frames):
            t = (i + 1) / down_frames
            if HAVE_PYTWEEN and hasattr(_pt, "easeOutCubic"):
                v = float(_pt.easeOutCubic(t))
            else:
                v = self._ease_out_cubic(t)
            factors.append(1.0 + (shrink_factor - 1.0) * v)

        for i in range(up_frames):
            t = (i + 1) / up_frames
            if HAVE_PYTWEEN and hasattr(_pt, "easeOutCubic"):
                v = float(_pt.easeOutCubic(t))
            else:
                v = self._ease_out_cubic(t)
            factors.append(shrink_factor + (overshoot - shrink_factor) * v)

        for i in range(settle_frames):
            t = (i + 1) / settle_frames
            if HAVE_PYTWEEN and hasattr(_pt, "easeOutBack"):
                v = float(_pt.easeOutBack(t))
            elif HAVE_EASING_LIB:
                try:
                    inst = _BackEaseOut(start=0, end=1, duration=1)  # type: ignore
                    v = float(inst.ease(t))
                except Exception:
                    v = self._ease_out_back(t, s=1.2)
            else:
                v = self._ease_out_back(t, s=1.2)
            factors.append(overshoot + (1.0 - overshoot) * v)

        if factors:
            factors[-1] = 1.0
        return factors

    def press_animation(self, widget, shrink_factor: float = 0.92, overshoot: float = 1.03,
                        dur_ms: int = 220, steps: int = 36):
        name = f"press_{id(widget)}"
        self.cancel(name)

        try:
            widget.update_idletasks()
            orig_w = int(widget.winfo_width())
            orig_h = int(widget.winfo_height())
        except Exception:
            orig_w = orig_h = 0

        if orig_w <= 2 or orig_h <= 2:
            return

        total_frames = max(6, steps)
        step_ms = max(4, dur_ms // total_frames)
        factors = self._compute_factors(total_frames, shrink_factor, overshoot)
        if factors and factors[-1] != 1.0:
            factors[-1] = 1.0

        def frame(i: int = 0):
            if i >= len(factors):
                try:
                    widget.configure(width=orig_w, height=orig_h)
                except Exception:
                    pass
                self._jobs.pop(name, None)
                return
            f = factors[i]
            new_w = max(1, int(orig_w * f))
            new_h = max(1, int(orig_h * f))
            try:
                widget.configure(width=new_w, height=new_h)
            except Exception:
                try:
                    widget.configure(width=orig_w, height=orig_h)
                except Exception:
                    pass
                self._jobs.pop(name, None)
                return
            self._jobs[name] = self.root.after(step_ms, lambda: frame(i + 1))

        frame(0)

    def animate_numeric_change(self, entry, start: float, end: float, steps: int = 8, step_ms: int = 25,
                               decimals: int = 5, use_comma: bool = True):
        name = f"animate_num_{id(entry)}"
        self.cancel(name)
        try:
            start_f = float(start)
            end_f = float(end)
        except Exception:
            txt = f"{end:.{decimals}f}" if isinstance(end, (int, float)) else str(end)
            if use_comma and isinstance(txt, str):
                txt = txt.replace(".", ",")
            try:
                entry.delete(0, "end"); entry.insert(0, txt)
            except Exception:
                pass
            return

        if steps <= 1:
            txt = f"{end_f:.{decimals}f}"
            if use_comma:
                txt = txt.replace(".", ",")
            try:
                entry.delete(0, "end"); entry.insert(0, txt)
            except Exception:
                pass
            return

        def frame(i: int):
            t = i / steps
            val = start_f + (end_f - start_f) * t
            txt = f"{val:.{decimals}f}"
            if use_comma:
                txt = txt.replace(".", ",")
            try:
                entry.delete(0, "end"); entry.insert(0, txt)
            except Exception:
                pass
            if i < steps:
                self.schedule(name, step_ms, lambda: frame(i + 1))
            else:
                final_txt = f"{end_f:.{decimals}f}"
                if use_comma:
                    final_txt = final_txt.replace(".", ",")
                try:
                    entry.delete(0, "end"); entry.insert(0, final_txt)
                except Exception:
                    pass
                self._jobs.pop(name, None)

# ---------------------------
# Improved Examples Generator (unique, pleasant, answer-type constraint)
# ---------------------------
def canonicalize_expr_ast(expr: str) -> str:
    """
    Return a structural canonical key for an expression using AST.
    Commutative binary ops (Add, Mult) are canonicalized by sorting operands.
    """
    try:
        node = ast.parse(expr, mode="eval").body
    except Exception:
        return "".join(expr.split())

    def node_key(n) -> str:
        if isinstance(n, ast.Constant):
            return repr(n.value)
        if isinstance(n, ast.Name):
            return n.id
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
            return ("u+" if isinstance(n.op, ast.UAdd) else "u-") + node_key(n.operand)
        if isinstance(n, ast.BinOp):
            left = node_key(n.left)
            right = node_key(n.right)
            op = type(n.op)
            if op in (ast.Add, ast.Mult):
                parts = sorted([left, right])
                return f"({op.__name__}:{parts[0]},{parts[1]})"
            else:
                return f"({op.__name__}:{left},{right})"
        return ast.dump(n, include_attributes=False)

    return node_key(node)

def _format_for_display(expr: str) -> str:
    s = expr.replace("**", "^")
    s = s.replace("*", " × ")
    s = s.replace("/", " ÷ ")
    s = " ".join(s.split())
    s = s.replace("^", " ^ ")
    s = " ".join(s.split())
    return s

def _int_with_digits(digits: int, allow_zero_leading: bool = False) -> int:
    digits = max(1, min(9, int(digits)))
    if digits == 1:
        lo, hi = (0, 9) if allow_zero_leading else (1, 9)
    else:
        lo = 10 ** (digits - 1)
        hi = 10 ** digits - 1
        if allow_zero_leading:
            lo = 0
    return random.randint(lo, hi)

def _decimal_operand(digits: int) -> str:
    int_part = _int_with_digits(max(1, min(digits, 6)))
    frac_len = random.randint(1, 3)
    frac = random.randint(0, 10**frac_len - 1)
    return f"{int_part}.{str(frac).zfill(frac_len)}"

def _is_integer_like(val: Union[int, float]) -> bool:
    try:
        if isinstance(val, int):
            return True
        if isinstance(val, float):
            return abs(val - round(val)) < 1e-9
        return False
    except Exception:
        return False

def _matches_answer_type(val: Union[int, float], answer_type: str) -> bool:
    if answer_type == "Любой":
        return True
    if answer_type == "Целое":
        return _is_integer_like(val)
    if answer_type == "Натуральное":
        return _is_integer_like(val) and val > 0
    if answer_type == "Неотрицательное":
        return _is_integer_like(val) and val >= 0
    if answer_type == "Дробное":
        return not _is_integer_like(val)
    return True

def generate_problems_improved(op_type: str, operand_digits: int, operands_count: int,
                               number_type: str, difficulty: str, count: int,
                               answer_type: str = "Любой", include_answers: bool = False) -> List[str]:
    """
    Generate unique, pleasant problems.
    answer_type: "Любой", "Целое", "Натуральное", "Неотрицательное", "Дробное"
    number_type: "digits","int","big","decimal"
    """
    operand_digits = max(1, min(12, int(operand_digits)))
    operands_count = max(2, min(5, int(operands_count)))
    count = max(1, min(500, int(count)))

    results: List[str] = []
    seen_keys = set()
    attempts = 0
    attempts_limit = max(1000, count * 50)

    def gen_operand(nt: str, digits: int) -> str:
        if nt == "digits":
            return str(random.randint(0, 9))
        if nt == "decimal":
            return _decimal_operand(digits)
        if nt == "big":
            return str(_int_with_digits(digits))
        return str(_int_with_digits(min(digits, 6)))

    def gen_div_pair(digits: int) -> Tuple[str, str]:
        divisor = random.randint(2, max(2, min(9, 10**min(1, digits) - 1)))
        multiplier = random.randint(1, max(2, 10**min(2, digits) - 1))
        numerator = divisor * multiplier
        return str(numerator), str(divisor)

    while len(results) < count and attempts < attempts_limit:
        attempts += 1

        if op_type == "Степень":
            base = gen_operand(number_type, min(operand_digits, 3))
            exponent = random.randint(2, 4 if operand_digits <= 3 else 3)
            expr_raw = f"{base}**{exponent}"
            key = canonicalize_expr_ast(expr_raw)
            if key in seen_keys:
                continue
            # Evaluate to check answer type
            try:
                val = safe_eval(expr_raw)
                if isinstance(val, complex):
                    continue
                if not _matches_answer_type(val, answer_type):
                    continue
                # skip too big results
                if isinstance(val, (int, float)) and abs(val) > 1e9:
                    continue
            except Exception:
                continue
            seen_keys.add(key)
            nice = _format_for_display(expr_raw)
            if include_answers:
                nice = f"{nice} = {val}"
            results.append(nice)
            continue

        op_map = {"Сложение": "+", "Вычитание": "-", "Умножение": "*", "Деление": "/"}
        if op_type == "Смешанные":
            ops = [random.choice(["+", "-", "*", "/"]) for _ in range(operands_count - 1)]
        else:
            ops = [op_map.get(op_type, "+")] * (operands_count - 1)

        operands: List[str] = []
        for i in range(operands_count):
            # handle division pleasance for easy
            if i < len(ops) and ops[i] == "/" and difficulty == "Лёгкая":
                a, b = gen_div_pair(operand_digits)
                # if first operand missing, append a then b
                if not operands:
                    operands.append(a)
                    # append denominator as next operand (it will be used below)
                    if len(operands) < operands_count:
                        operands.append(b)
                else:
                    operands.append(b)
            else:
                opnd = gen_operand(number_type, operand_digits)
                # avoid trivial repeat
                if len(operands) > 0 and opnd == operands[-1] and random.random() < 0.6:
                    opnd = gen_operand(number_type, operand_digits)
                operands.append(opnd)

        operands = operands[:operands_count]

        parts: List[str] = []
        for i, val in enumerate(operands):
            parts.append(val)
            if i < len(ops):
                parts.append(ops[i])
        expr_raw = " ".join(parts)

        # occasionally add parentheses for challenge
        if difficulty == "Сложная" and random.random() < 0.6 and operands_count >= 3:
            tokens = expr_raw.split()
            operand_indices = [i for i in range(0, len(tokens), 2)]
            if len(operand_indices) >= 2:
                s_idx = random.choice(operand_indices[:-1])
                e_idx = random.choice([i for i in operand_indices if i > s_idx])
                tokens[s_idx] = "(" + tokens[s_idx]
                tokens[e_idx] = tokens[e_idx] + ")"
                expr_raw = " ".join(tokens)

        # quick sanity
        compact = expr_raw.replace(" ", "")
        if any(ch not in "0123456789+-*/()." for ch in compact):
            # allow decimal dot and parentheses; skip malformed
            continue

        key = canonicalize_expr_ast(expr_raw)
        if key in seen_keys:
            continue

        # Evaluate and enforce answer type
        try:
            val = safe_eval(expr_raw)
            if isinstance(val, complex):
                continue
            # Discard extremely large results
            if isinstance(val, (int, float)) and abs(val) > 1e9:
                continue
            if not _matches_answer_type(val, answer_type):
                continue
        except Exception:
            # skip expressions that fail to evaluate safely
            continue

        seen_keys.add(key)
        nice = _format_for_display(expr_raw)
        if include_answers:
            nice = f"{nice} = {val}"
        results.append(nice)

    return results

# ---------------------------
# Calculator App (includes Examples window)
# ---------------------------
class CalculatorApp:
    FIGURES_MAP: Dict[str, List[str]] = {
        "Прямоугольник": ["Длина", "Ширина"],
        "Круг": ["Радиус"],
        "Треуг. (осн.,выс.)": ["Основание", "Высота"],
        "Треуг. (3 стороны)": ["a", "b", "c"],
        "Куб": ["a"],
        "Параллелепипед": ["Длина", "Ширина", "Высота"],
        "Шар": ["R"],
        "Цилиндр": ["R", "H"],
        "Конус": ["R", "H"],
        "Пирамида": ["Sосн", "H"],
    }

    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("Калькулятор — Smooth Animations")
        self.root.geometry(f"{CFG.win_w}x{CFG.win_h}")
        self.root.resizable(*CFG.resizable)
        try:
            self.root.wm_attributes("-alpha", 0.0)
        except Exception:
            pass

        self.anim = Animator(self.root)
        try:
            self.anim.fade_in(self.root, target_alpha=CFG.win_alpha, duration=260, steps=14)
        except Exception:
            pass

        self.max_input_chars = CFG.max_input
        self._hover_cache: Dict[str, str] = {}
        self._accent_buttons: List[ctk.CTkButton] = []
        self._build_ui()

        for b in self._accent_buttons:
            try:
                self._pulse_color(b, CFG.accent, min_factor=0.9, max_factor=1.12, period_ms=1600, steps=26)
            except Exception:
                pass

        self.root.bind("<Return>", lambda e: self._on_press("="))
        self.root.bind("<BackSpace>", lambda e: self.backspace())
        self.root.bind("<Escape>", lambda e: self.clear_all())

    def _copy_to_clipboard(self, text: str):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            try:
                self.root.update()
            except Exception:
                pass
            self._show_message("Копирование", "Скопировано в буфер обмена")
        except Exception:
            try:
                messagebox.showinfo("Копирование", "Копирование не удалось", parent=self.root)
            except Exception:
                pass

    def _attach_copy_context(self, widget, get_text: Callable[[], str]):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Копировать", command=lambda: self._copy_to_clipboard(get_text()))
        def show_menu(event):
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                try:
                    menu.grab_release()
                except Exception:
                    pass
        try:
            widget.bind("<Button-3>", show_menu)
            widget.bind("<Button-2>", show_menu)
            widget.bind("<Control-c>", lambda e: self._copy_to_clipboard(get_text()))
            widget.bind("<Control-C>", lambda e: self._copy_to_clipboard(get_text()))
        except Exception:
            pass

    def _hover_cached(self, color: str) -> str:
        if color not in self._hover_cache:
            self._hover_cache[color] = hover_color(color)
        return self._hover_cache[color]

    def _create_button(self, parent, text: str, fg_color: str, command: Callable[[], None], width: Optional[int] = None) -> ctk.CTkButton:
        btn = ctk.CTkButton(parent, text=text, corner_radius=CFG.btn_corner, fg_color=fg_color,
                            hover_color=self._hover_cached(fg_color), height=CFG.btn_h,
                            font=FONTS["ui"], command=command, text_color=CFG.text)
        if width:
            try:
                btn.configure(width=width)
            except Exception:
                pass
        return btn

    def _attach_focus_highlight(self, entry: ctk.CTkEntry):
        try:
            orig = entry.cget("fg_color")
            focused = adjust_brightness(orig, 1.12)
        except Exception:
            orig = CFG.surface
            focused = adjust_brightness(orig, 1.12)
        try:
            entry.bind("<FocusIn>", lambda e: entry.configure(fg_color=focused))
            entry.bind("<FocusOut>", lambda e: entry.configure(fg_color=orig))
        except Exception:
            pass

    def _build_ui(self):
        pad = CFG.container_pad
        container = ctk.CTkFrame(self.root, corner_radius=8, fg_color=CFG.panel)
        container.pack(fill="both", expand=True, padx=pad, pady=pad)
        self.container = container

        top_frame = ctk.CTkFrame(container, fg_color=container.cget("fg_color"), corner_radius=0)
        top_frame.grid(row=0, column=0, columnspan=4, padx=10, pady=(12, 6), sticky="we")

        self.entry_var = tk.StringVar()
        self.display = ctk.CTkEntry(top_frame, textvariable=self.entry_var, corner_radius=6,
                                    fg_color=CFG.surface, text_color=CFG.text, height=CFG.entry_h,
                                    font=FONTS["bold"])
        self.display.pack(side="left", fill="x", expand=True)
        self._attach_focus_highlight(self.display)

        copy_main_btn = ctk.CTkButton(top_frame, text="⟡", width=max(32, min(42, CFG.entry_h)), height=max(32, min(42, CFG.entry_h)),
                                      corner_radius=8, fg_color=CFG.accent_alt, hover_color=self._hover_cached(CFG.accent_alt),
                                      font=FONTS["small"], text_color=CFG.text,
                                      command=lambda: self._copy_to_clipboard(self.entry_var.get()))
        copy_main_btn.pack(side="right", padx=(8, 0))

        self._attach_copy_context(self.display, lambda: self.entry_var.get())

        keys = [
            ("7", "8", "9", "/"),
            ("4", "5", "6", "*"),
            ("1", "2", "3", "-"),
            ("0", ".", "=", "+"),
        ]
        for r, row in enumerate(keys, start=1):
            for c, key in enumerate(row):
                fg = CFG.card
                if key == "=":
                    fg = CFG.accent
                elif key in "+-*/%":
                    fg = CFG.accent_alt
                btn = self._create_button(container, key, fg, lambda ch=key: self._on_press(ch))
                btn.configure(command=lambda b=btn, ch=key: (self.anim.press_animation(b, shrink_factor=0.92, overshoot=1.03, dur_ms=220, steps=36), self._on_press(ch)))
                btn.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")
                if fg == CFG.accent:
                    self._accent_buttons.append(btn)

        specials = [
            ("C", self.clear_all, CFG.accent_alt),
            ("⌫", self.backspace, CFG.card),
            ("xʸ", self.power_window, CFG.card),
            ("□", self.figures_window_compact_centered, CFG.accent_alt),
        ]
        for i, (txt, cmd, color) in enumerate(specials):
            btn = self._create_button(container, txt, color, cmd)
            btn.configure(command=lambda b=btn, fn=cmd: (self.anim.press_animation(b, shrink_factor=0.92, overshoot=1.03, dur_ms=220, steps=36), self.root.after(110, fn)))
            btn.grid(row=5, column=i, padx=6, pady=(6, 10), sticky="nsew")
            if color == CFG.accent:
                self._accent_buttons.append(btn)

        for i in range(4):
            container.grid_columnconfigure(i, weight=1)

        # Footer: label + Examples button
        footer_frame = ctk.CTkFrame(container, fg_color=container.cget("fg_color"))
        footer_frame.grid(row=6, column=0, columnspan=4, pady=(0, 8), sticky="we")
        footer_frame.grid_columnconfigure(0, weight=1)
        footer_frame.grid_columnconfigure(1, weight=0)
        footer = ctk.CTkLabel(footer_frame, text="Compact • Smooth • Dark", text_color=CFG.muted, anchor="w", font=FONTS["ui"])
        footer.grid(row=0, column=0, sticky="w", padx=(8, 0))
        examples_btn = ctk.CTkButton(footer_frame, text="Примеры", fg_color=CFG.accent_alt, width=100, corner_radius=6,
                                     command=self.examples_window, font=FONTS["ui"], text_color=CFG.text, hover_color=self._hover_cached(CFG.accent_alt))
        examples_btn.grid(row=0, column=1, sticky="e", padx=(0, 8))

    def _on_press(self, ch: str):
        if ch == "=":
            self.evaluate(); return
        cur = self.entry_var.get()
        if len(cur) >= self.max_input_chars:
            return
        try:
            self.display.insert("end", ch)
        except Exception:
            self.entry_var.set(cur + ch)

    def evaluate(self):
        expr = self.entry_var.get().strip()
        if not expr:
            return
        try:
            result = safe_eval(expr)
            s = str(result)
            self.display.delete(0, "end")
            if len(s) > 32:
                self.display.insert(0, "Результат слишком длинный")
                self._show_full_result(s)
            else:
                self.display.insert(0, s)
        except ValueError as ve:
            self._show_message("Ошибка", str(ve) or "Неверное выражение", is_error=True)
        except Exception:
            self._show_message("Ошибка", "Неверное выражение", is_error=True)

    def clear_all(self):
        try:
            self.display.delete(0, "end")
        except Exception:
            self.entry_var.set("")

    def backspace(self):
        cur = self.entry_var.get()
        if not cur:
            return
        try:
            self.display.delete(len(cur) - 1, "end")
        except Exception:
            try:
                self.display.delete(max(0, len(cur) - 1), "end")
            except Exception:
                self.entry_var.set(cur[:-1])

    def _show_message(self, title: str, message: str, is_error: bool = False):
        win = ctk.CTkToplevel(self.root)
        win.title(title)
        win.geometry("320x120")
        win.transient(self.root); win.grab_set()
        try:
            win.attributes("-alpha", 0.0)
        except Exception:
            pass
        try:
            self.anim.fade_in(win, target_alpha=1.0, duration=220, steps=12)
        except Exception:
            pass
        frame = ctk.CTkFrame(win, corner_radius=8, fg_color=CFG.panel)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        lbl = ctk.CTkLabel(frame, text=message, wraplength=280,
                           text_color=("#ffb4b4" if is_error else CFG.text), font=FONTS["ui"])
        lbl.pack(pady=(8, 8))
        ctk.CTkButton(frame, text="Закрыть", fg_color=CFG.accent, command=win.destroy, font=FONTS["ui"], text_color=CFG.text).pack(pady=(0, 6))

    def _show_full_result(self, text: str):
        win = ctk.CTkToplevel(self.root)
        win.title("Результат (полный)")
        win.geometry("520x300")
        win.transient(self.root); win.grab_set()
        try:
            win.attributes("-alpha", 0.0)
        except Exception:
            pass
        try:
            self.anim.fade_in(win, target_alpha=1.0, duration=260, steps=14)
        except Exception:
            pass
        frame = ctk.CTkFrame(win, corner_radius=8, fg_color=CFG.panel)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        txt = ctk.CTkTextbox(frame, width=480, height=220, corner_radius=6, fg_color=CFG.surface, font=FONTS["ui"])
        txt.pack(expand=True, fill="both", padx=6, pady=6)
        txt.insert("0.0", text)
        try:
            txt.configure(state="normal")
            txt.bind("<Control-a>", lambda e: (txt.tag_add("sel", "1.0", "end"), "break"))
        except Exception:
            pass
        btns_frame = ctk.CTkFrame(frame, fg_color=frame.cget("fg_color"))
        btns_frame.pack(fill="x", pady=(6, 0))
        copy_btn = ctk.CTkButton(btns_frame, text="⟡", fg_color=CFG.accent_alt, width=36, height=36, corner_radius=8,
                                 command=lambda: self._copy_to_clipboard(txt.get("0.0", "end").strip()),
                                 font=FONTS["small"], text_color=CFG.text, hover_color=self._hover_cached(CFG.accent_alt))
        copy_btn.pack(side="left", padx=(6, 6))
        close_btn = ctk.CTkButton(btns_frame, text="Закрыть", fg_color=CFG.accent,
                                  command=win.destroy, font=FONTS["ui"], text_color=CFG.text)
        close_btn.pack(side="right", padx=(6, 6))

    def power_window(self):
        win_w, win_h = 360, 260
        win = ctk.CTkToplevel(self.root)
        win.title("Степень xʸ")
        try:
            rx = self.root.winfo_rootx(); ry = self.root.winfo_rooty()
            rw = self.root.winfo_width(); rh = self.root.winfo_height()
            x = rx + max(0, (rw - win_w) // 2); y = ry + max(0, (rh - win_h) // 2)
            win.geometry(f"{win_w}x{win_h}+{x}+{y}")
        except Exception:
            sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
            x = (sw - win_w) // 2; y = (sh - win_h) // 2
            win.geometry(f"{win_w}x{win_h}+{x}+{y}")
        win.resizable(False, False)
        win.transient(self.root); win.grab_set()
        try:
            win.attributes("-alpha", 0.0)
        except Exception:
            pass
        try:
            self.anim.fade_in(win, target_alpha=1.0, duration=220, steps=12)
        except Exception:
            pass

        f = ctk.CTkFrame(win, corner_radius=6, fg_color=CFG.panel)
        f.pack(fill="both", expand=True, padx=10, pady=10)

        inputs = ctk.CTkFrame(f, fg_color=f.cget("fg_color"))
        inputs.pack(fill="both", expand=True, pady=(0, 6))

        ctk.CTkLabel(inputs, text="x (основание):", font=FONTS["ui"], text_color=CFG.text).pack(anchor="w", pady=(6, 2))
        ex = ctk.CTkEntry(inputs, corner_radius=6, font=FONTS["ui"], fg_color=CFG.surface, text_color=CFG.text, height=CFG.compact_entry_h)
        ex.pack(fill="x", pady=(0, 6)); self._attach_focus_highlight(ex)

        ctk.CTkLabel(inputs, text="y (показатель):", font=FONTS["ui"], text_color=CFG.text).pack(anchor="w", pady=(6, 2))
        ey = ctk.CTkEntry(inputs, corner_radius=6, font=FONTS["ui"], fg_color=CFG.surface, text_color=CFG.text, height=CFG.compact_entry_h)
        ey.pack(fill="x", pady=(0, 6)); self._attach_focus_highlight(ey)

        res_lbl = ctk.CTkLabel(inputs, text="", text_color=CFG.text, wraplength=300, justify="left", font=FONTS["ui"])
        res_lbl.pack(fill="x", pady=(6, 2))
        self._attach_copy_context(res_lbl, lambda r=res_lbl: r.cget("text"))

        bottom_frame = ctk.CTkFrame(f, fg_color=f.cget("fg_color"))
        bottom_frame.pack(side="bottom", fill="x")
        bottom_frame.configure(height=70)
        bottom_frame.pack_propagate(False)

        btn = ctk.CTkButton(bottom_frame, text="Вычислить", fg_color=CFG.accent, width=200, corner_radius=6,
                            font=FONTS["ui"], text_color=CFG.text, hover_color=self._hover_cached(CFG.accent))
        btn.pack(side="right", padx=(0, 8), pady=(10, 10))

        copy_power_btn = ctk.CTkButton(bottom_frame, text="⟡", fg_color=CFG.accent_alt, width=36, height=36, corner_radius=8,
                                       font=FONTS["small"], text_color=CFG.text,
                                       command=lambda: self._copy_to_clipboard(res_lbl.cget("text")),
                                       hover_color=self._hover_cached(CFG.accent_alt))
        copy_power_btn.pack(side="left", padx=(8, 8), pady=(10, 10))

        def compute_and_show():
            self.anim.press_animation(btn)
            try:
                x = parse_number(ex.get().strip())
                y = parse_number(ey.get().strip())
                if isinstance(x, complex) or isinstance(y, complex):
                    res_lbl.configure(text="Комплексные показатели не поддерживаются здесь", text_color="#ffb4b4")
                else:
                    res = float(x) ** float(y)
                    formatted = repr(res)
                    short = formatted if len(formatted) <= 64 else (formatted[:61] + "...")
                    res_lbl.configure(text=f"Результат: {short}", text_color=CFG.text)
                    if len(formatted) > 64:
                        self._show_full_result(formatted)
            except ValueError:
                res_lbl.configure(text="Ошибка ввода: ожидаются числа", text_color="#ffb4b4")
            except OverflowError:
                res_lbl.configure(text="Ошибка: переполнение результата", text_color="#ffb4b4")
            except Exception:
                res_lbl.configure(text="Ошибка при вычислении", text_color="#ffb4b4")
            finally:
                btn.configure(text="Вычислить")

        btn.configure(command=compute_and_show)

    def figures_window_compact_centered(self):
        win_w, win_h = 520, 260
        win = ctk.CTkToplevel(self.root)
        win.title("Фигуры — компактно")
        try:
            rx = self.root.winfo_rootx(); ry = self.root.winfo_rooty()
            rw = self.root.winfo_width(); rh = self.root.winfo_height()
            x = rx + max(0, (rw - win_w) // 2); y = ry + max(0, (rh - win_h) // 2)
            win.geometry(f"{win_w}x{win_h}+{x}+{y}")
        except Exception:
            sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
            x = (sw - win_w) // 2; y = (sh - win_h) // 2
            win.geometry(f"{win_w}x{win_h}+{x}+{y}")
        win.resizable(False, False)
        win.transient(self.root); win.grab_set()
        try:
            win.attributes("-alpha", 0.0)
        except Exception:
            pass
        try:
            self.anim.fade_in(win, target_alpha=1.0, duration=220, steps=12)
        except Exception:
            pass

        main = ctk.CTkFrame(win, corner_radius=8, fg_color=CFG.panel)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        top = ctk.CTkFrame(main, corner_radius=6, fg_color=CFG.surface)
        top.pack(fill="x", padx=6, pady=(6, 8))
        top.grid_columnconfigure(0, weight=1); top.grid_columnconfigure(1, weight=0)
        ctk.CTkLabel(top, text="Фигура", font=FONTS["ui"], text_color=CFG.text).grid(row=0, column=0, sticky="e", padx=(0, 6))

        names = list(self.FIGURES_MAP.keys())
        fields_frame = ctk.CTkFrame(main, corner_radius=6, fg_color=CFG.panel)
        fields_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        choice = ctk.CTkOptionMenu(top, values=names, width=300, fg_color=CFG.surface, button_color=CFG.accent_alt,
                                   text_color=CFG.text, dropdown_fg_color=("#f3f3f3", CFG.surface),
                                   dropdown_text_color=("#333333", CFG.text), corner_radius=6, font=FONTS["ui"],
                                   command=lambda v: self._populate_fields_for_figure_centered(v, fields_frame))
        choice.set(names[0])
        choice.grid(row=0, column=1, sticky="w", padx=(6, 0))

        self._populate_fields_for_figure_centered(names[0], fields_frame)

    def _populate_fields_for_figure_centered(self, figure_name: str, container: ctk.CTkFrame):
        for w in container.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass

        fields = self.FIGURES_MAP.get(figure_name, [])
        entries: List[ctk.CTkEntry] = []

        inner = ctk.CTkFrame(container, fg_color=container.cget("fg_color"))
        inner.pack(fill="both", expand=True, padx=4, pady=2)

        inputs_holder = ctk.CTkFrame(inner, fg_color=inner.cget("fg_color"))
        inputs_holder.pack(fill="x", side="top", pady=(2, 4))

        bottom_frame = ctk.CTkFrame(inner, fg_color=inner.cget("fg_color"))
        bottom_frame.pack(side="bottom", fill="x", pady=(4, 2))

        if not fields:
            ctk.CTkLabel(inputs_holder, text="Нет параметров для этой фигуры", font=FONTS["ui"], text_color=CFG.muted).pack(padx=8, pady=6)
        else:
            for f in fields:
                row = ctk.CTkFrame(inputs_holder, fg_color=inputs_holder.cget("fg_color"))
                row.pack(fill="x", padx=6, pady=2)
                ctk.CTkLabel(row, text=f + ":", width=70, anchor="e", font=FONTS["ui"], text_color=CFG.text).pack(side="left", padx=(0, 8))
                ctrl = ctk.CTkFrame(row, fg_color=row.cget("fg_color"))
                ctrl.pack(side="left", fill="x", expand=True, padx=(0, 6))
                e = ctk.CTkEntry(ctrl, corner_radius=6, font=FONTS["ui"], fg_color=CFG.surface, text_color=CFG.text,
                                height=CFG.compact_entry_h, width=260)
                e.pack(side="left", fill="x", expand=True)
                self._attach_focus_highlight(e)
                spin_bg = ctrl.cget("fg_color")
                spin_frame = ctk.CTkFrame(ctrl, fg_color=spin_bg)
                spin_frame.pack(side="right", padx=(8, 0), pady=0)
                btn_w = 36
                common_opts = dict(width=btn_w, height=CFG.compact_entry_h, corner_radius=6,
                                   fg_color=spin_bg, hover_color=spin_bg,
                                   font=FONTS["small"], text_color=CFG.text, border_width=0)
                btn_dec = ctk.CTkButton(spin_frame, text="▼", **common_opts)
                btn_dec.pack(side="right", padx=(6, 0))
                btn_inc = ctk.CTkButton(spin_frame, text="▲", **common_opts)
                btn_inc.pack(side="right")
                if not e.get().strip():
                    e.insert(0, format_number(0, decimals=0))
                def make_spin_handlers(entry: ctk.CTkEntry, step: float = 1.0, decimals: int = 0):
                    def inc():
                        try:
                            v = parse_number(entry.get())
                            if isinstance(v, complex):
                                return
                            start = int(round(float(v)))
                            target = start + int(round(step))
                            self.anim.animate_numeric_change(entry, start, target, steps=9, step_ms=22, decimals=decimals)
                        except Exception:
                            entry.delete(0, "end"); entry.insert(0, format_number(step, decimals=decimals))
                    def dec():
                        try:
                            v = parse_number(entry.get())
                            if isinstance(v, complex):
                                return
                            start = int(round(float(v)))
                            target = start - int(round(step))
                            self.anim.animate_numeric_change(entry, start, target, steps=9, step_ms=22, decimals=decimals)
                        except Exception:
                            entry.delete(0, "end"); entry.insert(0, format_number(0, decimals=decimals))
                    return inc, dec
                inc_fn, dec_fn = make_spin_handlers(e, step=1.0, decimals=0)
                btn_inc.configure(command=lambda b=btn_inc, fn=inc_fn: (self.anim.press_animation(b), self.root.after(80, fn)))
                btn_dec.configure(command=lambda b=btn_dec, fn=dec_fn: (self.anim.press_animation(b), self.root.after(80, fn)))
                self._attach_copy_context(e, lambda ent=e: ent.get())
                entries.append(e)

        res_lbl = ctk.CTkLabel(bottom_frame, text="", text_color=CFG.text, wraplength=420, justify="left", font=FONTS["ui"])
        res_lbl.pack(side="left", padx=(6, 4))
        self._attach_copy_context(res_lbl, lambda r=res_lbl: r.cget("text"))

        def compute_and_show():
            try:
                vals = [entry.get() for entry in entries]
                def getf(i: int) -> float:
                    v = parse_number(vals[i])
                    if isinstance(v, complex):
                        raise ValueError("Требуется вещественное число")
                    return float(v)
                area = peri = vol = None
                name = figure_name
                if name == "Прямоугольник":
                    a = getf(0); b = getf(1); area = a * b; peri = 2 * (a + b)
                elif name == "Круг":
                    r = getf(0); area = math.pi * r * r; peri = 2 * math.pi * r
                elif name == "Треуг. (осн.,выс.)":
                    a = getf(0); h = getf(1); area = 0.5 * a * h
                elif name == "Треуг. (3 стороны)":
                    a = getf(0); b = getf(1); c = getf(2); peri = a + b + c
                elif name == "Куб":
                    a = getf(0); area = 6 * a * a; vol = a ** 3
                elif name == "Параллелепипед":
                    a = getf(0); b = getf(1); c = getf(2); area = 2 * (a * b + b * c + a * c); vol = a * b * c
                elif name == "Шар":
                    r = getf(0); area = 4 * math.pi * r * r; vol = 4.0 / 3.0 * math.pi * r ** 3
                elif name == "Цилиндр":
                    r = getf(0); h = getf(1); area = 2 * math.pi * r * (r + h); vol = math.pi * r * r * h
                elif name == "Конус":
                    r = getf(0); h = getf(1); slant = math.sqrt(r * r + h * h); area = math.pi * r * (r + slant); vol = 1.0 / 3.0 * math.pi * r * r * h
                elif name == "Пирамида":
                    S = getf(0); h = getf(1); vol = 1.0 / 3.0 * S * h
                parts: List[str] = []
                if area is not None:
                    parts.append(f"📐 Площадь: {area:.4f}")
                if peri is not None:
                    parts.append(f"📏 Периметр/Стороны: {peri:.4f}")
                if vol is not None:
                    parts.append(f"📦 Объём: {vol:.4f}")
                res_lbl.configure(text="\n".join(parts) if parts else "Нет данных для выбранной фигуры", text_color=CFG.text)
            except ValueError:
                res_lbl.configure(text="Ошибка ввода: ожидаются числа", text_color="#ffb4b4")
            except Exception:
                res_lbl.configure(text="Ошибка при вычислении", text_color="#ffb4b4")

        copy_fig_btn = ctk.CTkButton(bottom_frame, text="⟡", fg_color=CFG.accent_alt, width=36, height=36, corner_radius=8,
                                     command=lambda: self._copy_to_clipboard(res_lbl.cget("text")),
                                     font=FONTS["small"], text_color=CFG.text, hover_color=self._hover_cached(CFG.accent_alt))
        copy_fig_btn.pack(side="right", padx=(6, 6), pady=(6, 4))

        calc_btn = ctk.CTkButton(bottom_frame, text="Вычислить", fg_color=CFG.accent, width=140, corner_radius=6,
                                command=lambda: (self.anim.press_animation(calc_btn), self.root.after(110, compute_and_show)),
                                font=FONTS["ui"], text_color=CFG.text, hover_color=self._hover_cached(CFG.accent))
        calc_btn.pack(side="right", padx=(0, 8), pady=(6, 4))

    def examples_window(self):
        win_w, win_h = 720, 520
        win = ctk.CTkToplevel(self.root)
        win.title("Генератор примеров")
        try:
            rx = self.root.winfo_rootx(); ry = self.root.winfo_rooty()
            rw = self.root.winfo_width(); rh = self.root.winfo_height()
            x = rx + max(0, (rw - win_w) // 2); y = ry + max(0, (rh - win_h) // 2)
            win.geometry(f"{win_w}x{win_h}+{x}+{y}")
        except Exception:
            sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
            x = (sw - win_w) // 2; y = (sh - win_h) // 2
            win.geometry(f"{win_w}x{win_h}+{x}+{y}")
        win.resizable(False, False)
        win.transient(self.root); win.grab_set()
        try:
            win.attributes("-alpha", 0.0)
        except Exception:
            pass
        try:
            self.anim.fade_in(win, target_alpha=1.0, duration=220, steps=12)
        except Exception:
            pass

        frame = ctk.CTkFrame(win, corner_radius=8, fg_color=CFG.panel)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        controls = ctk.CTkFrame(frame, fg_color=frame.cget("fg_color"))
        controls.pack(fill="x", padx=6, pady=(6, 8))

        ctk.CTkLabel(controls, text="Тип операции:", font=FONTS["ui"], text_color=CFG.text).grid(row=0, column=0, sticky="w", padx=(6,4), pady=6)
        op_values = ["Сложение", "Вычитание", "Умножение", "Деление", "Степень", "Смешанные"]
        op_choice = ctk.CTkOptionMenu(controls, values=op_values, width=180, fg_color=CFG.surface, button_color=CFG.accent_alt,
                                      text_color=CFG.text, corner_radius=6, font=FONTS["ui"])
        op_choice.set(op_values[0])
        op_choice.grid(row=0, column=1, sticky="w", padx=(0,6), pady=6)

        ctk.CTkLabel(controls, text="Цифр в операнде:", font=FONTS["ui"], text_color=CFG.text).grid(row=1, column=0, sticky="w", padx=(6,4), pady=6)
        digits_entry = ctk.CTkEntry(controls, width=100, height=CFG.compact_entry_h, corner_radius=6, fg_color=CFG.surface, text_color=CFG.text, font=FONTS["ui"])
        digits_entry.insert(0, "2")
        digits_entry.grid(row=1, column=1, sticky="w", padx=(0,6), pady=6)

        ctk.CTkLabel(controls, text="Кол-во операндов:", font=FONTS["ui"], text_color=CFG.text).grid(row=0, column=2, sticky="w", padx=(12,4), pady=6)
        operands_spin = ctk.CTkOptionMenu(controls, values=["2","3","4","5"], width=80, fg_color=CFG.surface, button_color=CFG.accent_alt,
                                          text_color=CFG.text, corner_radius=6, font=FONTS["ui"])
        operands_spin.set("2")
        operands_spin.grid(row=0, column=3, sticky="w", padx=(0,6), pady=6)

        ctk.CTkLabel(controls, text="Сложность:", font=FONTS["ui"], text_color=CFG.text).grid(row=1, column=2, sticky="w", padx=(12,4), pady=6)
        diff_choice = ctk.CTkOptionMenu(controls, values=["Лёгкая","Средняя","Сложная"], width=120, fg_color=CFG.surface, button_color=CFG.accent_alt,
                                        text_color=CFG.text, corner_radius=6, font=FONTS["ui"])
        diff_choice.set("Лёгкая")
        diff_choice.grid(row=1, column=3, sticky="w", padx=(0,6), pady=6)

        ctk.CTkLabel(controls, text="Тип чисел:", font=FONTS["ui"], text_color=CFG.text).grid(row=2, column=0, sticky="w", padx=(6,4), pady=6)
        num_types = ["Цифры (0-9)","Целые","Большие целые","Десятичные"]
        num_choice = ctk.CTkOptionMenu(controls, values=num_types, width=180, fg_color=CFG.surface, button_color=CFG.accent_alt,
                                       text_color=CFG.text, corner_radius=6, font=FONTS["ui"])
        num_choice.set(num_types[1])
        num_choice.grid(row=2, column=1, sticky="w", padx=(0,6), pady=6)

        ctk.CTkLabel(controls, text="Кол-во примеров:", font=FONTS["ui"], text_color=CFG.text).grid(row=2, column=2, sticky="w", padx=(12,4), pady=6)
        count_entry = ctk.CTkEntry(controls, width=80, height=CFG.compact_entry_h, corner_radius=6, fg_color=CFG.surface, text_color=CFG.text, font=FONTS["ui"])
        count_entry.insert(0, "10")
        count_entry.grid(row=2, column=3, sticky="w", padx=(0,6), pady=6)

        # New: answer type
        ctk.CTkLabel(controls, text="Тип ответа:", font=FONTS["ui"], text_color=CFG.text).grid(row=3, column=0, sticky="w", padx=(6,4), pady=6)
        answer_types = ["Любой", "Целое", "Натуральное", "Неотрицательное", "Дробное"]
        answer_choice = ctk.CTkOptionMenu(controls, values=answer_types, width=180, fg_color=CFG.surface, button_color=CFG.accent_alt,
                                          text_color=CFG.text, corner_radius=6, font=FONTS["ui"])
        answer_choice.set(answer_types[0])
        answer_choice.grid(row=3, column=1, sticky="w", padx=(0,6), pady=6)

        include_answers_var = tk.BooleanVar(value=False)
        include_answers_chk = ctk.CTkCheckBox(controls, text="Включать ответы в текст", variable=include_answers_var, fg_color=CFG.accent, text_color=CFG.text, width=220)
        include_answers_chk.grid(row=3, column=2, columnspan=2, sticky="w", padx=(12,0), pady=6)

        actions = ctk.CTkFrame(frame, fg_color=frame.cget("fg_color"))
        actions.pack(fill="x", padx=6, pady=(0,8))

        gen_btn = ctk.CTkButton(actions, text="Создать", fg_color=CFG.accent, width=140, corner_radius=6,
                                font=FONTS["ui"], text_color=CFG.text)
        gen_btn.pack(side="right", padx=(0,8))

        copy_all_btn = ctk.CTkButton(actions, text="Копировать всё", fg_color=CFG.accent_alt, width=140, corner_radius=6,
                                     font=FONTS["ui"], text_color=CFG.text)
        copy_all_btn.pack(side="right", padx=(0,8))

        out_frame = ctk.CTkFrame(frame, fg_color=CFG.surface, corner_radius=6)
        out_frame.pack(fill="both", expand=True, padx=6, pady=(0,6))
        out_text = ctk.CTkTextbox(out_frame, width=680, height=320, corner_radius=6, fg_color=CFG.surface, font=FONTS["ui"])
        out_text.pack(expand=True, fill="both", padx=6, pady=6)
        out_text.configure(state="normal")

        info_lbl = ctk.CTkLabel(frame, text="Двойной клик по строке — скопировать её. Можно включить ответы.", font=FONTS["ui"], text_color=CFG.muted)
        info_lbl.pack(anchor="w", padx=8, pady=(0,6))

        num_type_map = {
            "Цифры (0-9)": "digits",
            "Целые": "int",
            "Большие целые": "big",
            "Десятичные": "decimal",
        }

        def do_generate():
            try:
                self.anim.press_animation(gen_btn)
            except Exception:
                pass
            op = op_choice.get()
            try:
                digits = int(digits_entry.get().strip())
            except Exception:
                digits = 2
            operands = int(operands_spin.get())
            difficulty = diff_choice.get()
            num_type = num_type_map.get(num_choice.get(), "int")
            try:
                cnt = int(count_entry.get().strip())
            except Exception:
                cnt = 10
            answer_type = answer_choice.get()
            include_answers = bool(include_answers_var.get())
            digits = max(1, min(12, digits))
            cnt = max(1, min(500, cnt))

            problems = generate_problems_improved(op, digits, operands, num_type, difficulty, cnt, answer_type, include_answers)

            try:
                out_text.configure(state="normal")
                out_text.delete("0.0", "end")
                for i, p in enumerate(problems, start=1):
                    out_text.insert("end", f"{i}. {p}\n")
                out_text.see("1.0")
            except Exception:
                try:
                    out_text.insert("end", "\n".join(problems))
                except Exception:
                    pass

        def do_copy_all():
            try:
                text = out_text.get("0.0", "end").strip()
                if text:
                    self._copy_to_clipboard(text)
                else:
                    messagebox.showinfo("Копирование", "Нет текста для копирования", parent=win)
            except Exception:
                try:
                    messagebox.showinfo("Копирование", "Не удалось скопировать", parent=win)
                except Exception:
                    pass

        def copy_selected_line(event=None):
            try:
                idx = out_text.index("insert")
                line = out_text.get(f"{idx} linestart", f"{idx} lineend").strip()
                if line:
                    self._copy_to_clipboard(line)
            except Exception:
                try:
                    messagebox.showinfo("Копирование", "Не удалось скопировать выбранную строку", parent=win)
                except Exception:
                    pass

        gen_btn.configure(command=lambda: (do_generate()))
        copy_all_btn.configure(command=lambda: (do_copy_all()))

        try:
            out_text.bind("<Double-Button-1>", lambda e: copy_selected_line(e))
            out_text.bind("<Control-c>", lambda e: copy_selected_line(e))
        except Exception:
            pass

        do_generate()

    def _pulse_color(self, widget: ctk.CTkButton, base_color: str, min_factor: float = 0.88, max_factor: float = 1.12,
                     period_ms: int = 1200, steps: int = 20):
        half = steps // 2
        step_ms = max(10, period_ms // steps)

        def frame(i: int = 0):
            if i < half:
                t = i / max(1, half - 1)
                factor = min_factor + (max_factor - min_factor) * t
            else:
                t = (i - half) / max(1, steps - half - 1)
                factor = max_factor - (max_factor - min_factor) * t
            try:
                widget.configure(fg_color=adjust_brightness(base_color, factor))
            except Exception:
                pass
            self.root.after(step_ms, lambda: frame((i + 1) % steps))

        frame(0)

    def run(self):
        self.root.mainloop()

# ---------------------------
# Run
# ---------------------------
if __name__ == "__main__":
    try:
        print("Optional libs: numpy={}, pytweening={}, easing-functions={}".format(HAVE_NUMPY, HAVE_PYTWEEN, HAVE_EASING_LIB))
    except Exception:
        pass
    CalculatorApp().run()
