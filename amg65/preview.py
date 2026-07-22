"""แสดง canvas 63×5 ในเทอร์มินัลด้วยสีจริง — พัฒนา scene ได้โดยไม่ต้องต่อคีย์บอร์ด

ใช้อักขระครึ่งบล็อก `▀` โดยให้สีตัวอักษรเป็นแถวบนและสีพื้นหลังเป็นแถวล่าง
จอ 5 แถวจึงย่อเหลือ 3 บรรทัด และได้อัตราส่วนใกล้ของจริงกว่าการพิมพ์แถวละบรรทัด
"""
from __future__ import annotations

import os
import sys

from .matrix import HEIGHT, WIDTH, Canvas

UPPER_HALF = "▀"
RESET = "\x1b[0m"


def enable_ansi() -> None:
    """เปิด VT processing ของ Windows console (Python จะพิมพ์ escape code ได้)."""
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def render_lines(canvas: Canvas) -> list[str]:
    """แปลง canvas เป็นข้อความ 3 บรรทัดพร้อมสี ANSI."""
    lines = []
    for top in range(0, HEIGHT, 2):
        parts = []
        for x in range(WIDTH):
            tr, tg, tb = canvas.get(x, top)
            br, bg, bb = canvas.get(x, top + 1) if top + 1 < HEIGHT else (0, 0, 0)
            parts.append(f"\x1b[38;2;{tr};{tg};{tb}m\x1b[48;2;{br};{bg};{bb}m{UPPER_HALF}")
        lines.append("".join(parts) + RESET)
    return lines


def draw(canvas: Canvas, status: str = "", home: bool = True) -> None:
    """พิมพ์ canvas ทับที่เดิม (home=True) เพื่อให้ดูเป็นภาพเคลื่อนไหว."""
    lines = render_lines(canvas)
    out = []
    if home:
        out.append("\x1b[H")
    out.append("┌" + "─" * WIDTH + "┐\n")
    for line in lines:
        out.append("│" + line + "│\n")
    out.append("└" + "─" * WIDTH + "┘\n")
    if status:
        out.append("\x1b[K" + status + "\n")
    sys.stdout.write("".join(out))
    sys.stdout.flush()


def clear_screen() -> None:
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()
