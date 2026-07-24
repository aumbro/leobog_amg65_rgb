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

        # **ทุกอย่างขยับเป็นสเต็ปครึ่งวินาที ไม่ไล่ต่อเฟรม** — ภาพจึงเหมือนเดิมเป๊ะ
        # ภายในแต่ละครึ่งวินาที ทำให้ frame-skip ตัดเฟรมซ้ำออกได้เกือบหมด
        # เหลือส่งจริงแค่ ~2 ครั้ง/วินาที = ทราฟฟิกต่ำสุด = โอกาสค้างต่ำสุด
        # (เดิมไล่เฉดสีทุกเฟรม แทบทุกเฟรมต่างกัน frame-skip เลยช่วยไม่ได้)
        half = int(now * 2)              # เปลี่ยนทุกครึ่งวินาที
        hue_base = (half * 0.03) % 1.0   # สีไล่ช้า ๆ แต่เป็นขั้น
        colon_dim = half % 2 == 0

        for module, char in enumerate(text):
            width = font.char_width(char)
            x0 = module * MODULE + (MODULE - width) // 2
            dim = char == ":" and colon_dim

            def color_of(_position: int, px: int, _py: int, dim=dim) -> tuple[int, int, int]:
                hue = (hue_base + px / 80.0) % 1.0
                r, g, b = colorsys.hsv_to_rgb(hue, 0.88, 0.42 if dim else 1.0)
                return int(r * 254), int(g * 254), int(b * 254)

            canvas.text(char, x0, color_of=color_of)

        # แผงขวา: invader ก้าวทุกครึ่งวินาทีเช่นกัน (เดิมทุก 3 เฟรม = ถี่กว่ามาก)
        invader = INVADER_FRAMES[half % len(INVADER_FRAMES)]
        r, g, b = colorsys.hsv_to_rgb(hue_base, 1.0, 1.0)
        color = (int(r * 254), int(g * 254), int(b * 254))
        for y, row in enumerate(invader):
            for dx, bit in enumerate(row):
                if bit == "1":
                    canvas.set(MAIN_WIDTH + dx, y, color)
