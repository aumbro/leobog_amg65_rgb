"""นาฬิกา HH:MM:SS บนแผงหลัก + Space Invader เต้นบนแผงขวา"""
from __future__ import annotations

import colorsys
import time

from .. import font
from ..matrix import MAIN_WIDTH, Canvas
from .base import Scene

INVADER_FRAMES = (
    ("0010100", "0111110", "1101011", "1111111", "0100010"),
    ("0010100", "0111110", "1101011", "1111111", "1000101"),
    ("0010100", "0111110", "1100011", "1111111", "0101010"),
    ("0010100", "0111110", "1101011", "1111111", "0011100"),
)

MODULE = 7  # แผงหลัก 56 px ÷ 8 ตัวอักษรของ "HH:MM:SS" = 7 px ต่อตัวพอดี


class ClockScene(Scene):
    name = "clock"
    description = "นาฬิกา HH:MM:SS + Space Invader"
    fps = 12.0

    def render(self, canvas: Canvas, elapsed: float, frame: int) -> None:
        now = time.time()
        text = time.strftime("%H:%M:%S")

        # จัดตัวอักษรลงช่อง 7 px ต่อตัว ไม่ให้ glyph คร่อมรอยต่อบล็อก 14×5 ของฮาร์ดแวร์
        for module, char in enumerate(text):
            width = font.char_width(char)
            x0 = module * MODULE + (MODULE - width) // 2
            dim = char == ":" and int(now * 2) % 2 == 0

            def color_of(_position: int, px: int, _py: int, dim=dim) -> tuple[int, int, int]:
                hue = (now * 0.075 + px / 80.0) % 1.0
                r, g, b = colorsys.hsv_to_rgb(hue, 0.88, 0.42 if dim else 1.0)
                return int(r * 254), int(g * 254), int(b * 254)

            canvas.text(char, x0, color_of=color_of)

        # แผงขวาแยกกายภาพจากแผงหลัก ให้มันมีชีวิตของตัวเอง
        invader = INVADER_FRAMES[(frame // 3) % len(INVADER_FRAMES)]
        r, g, b = colorsys.hsv_to_rgb((now * 0.20) % 1.0, 1.0, 1.0)
        color = (int(r * 254), int(g * 254), int(b * 254))
        for y, row in enumerate(invader):
            for dx, bit in enumerate(row):
                if bit == "1":
                    canvas.set(MAIN_WIDTH + dx, y, color)
