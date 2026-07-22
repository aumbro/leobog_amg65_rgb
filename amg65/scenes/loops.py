"""scene ที่ออกแบบมาให้วนลูปเนียนพอดี สำหรับเบคเก็บลงเครื่อง

จอนี้เล่นแอนิเมชันที่เก็บไว้ได้ถึง 83 FPS (เทียบกับ live stream ที่ตันแค่ 5-6)
แต่ของที่จะเก็บต้องวนกลับมาเหมือนเดิมพอดี ไม่งั้นภาพกระโดดทุกครั้งที่วน

เคล็ดลับที่ใช้ทั้งไฟล์: **คิดเวลาเป็นสัดส่วนของลูป ไม่ใช่วินาที**

    p = elapsed / loop_seconds        # 0 → 1 ตลอดหนึ่งลูป

แล้วให้ทุกพจน์ที่ขึ้นกับเวลาใช้ `sin(2πkp)` โดย k เป็นจำนวนเต็ม
ทุกพจน์จึงครบรอบพร้อมกันเป๊ะที่ p = 1 ลูปต่อเนียนโดยไม่ต้องจูนเลข
"""
from __future__ import annotations

import colorsys
import math

from ..matrix import HEIGHT, WIDTH, Canvas
from .base import Scene

TAU = math.tau


def _wheel(steps: int = 256) -> list[tuple[int, int, int]]:
    return [
        tuple(int(c * 254) for c in colorsys.hsv_to_rgb(i / steps, 1.0, 1.0))  # type: ignore[misc]
        for i in range(steps)
    ]


class PlasmaScene(Scene):
    name = "plasma"
    description = "คลื่นสีไหลนุ่ม ๆ วนลูปเนียน (เหมาะกับ upload)"
    fps = 30.0
    loop_seconds = 6.0

    # ตัวคูณเวลาของแต่ละคลื่น ต้องเป็นจำนวนเต็มเพื่อให้ครบรอบพร้อมกันที่ p = 1
    # เลือกให้ไม่ลงตัวกัน (1,2,3,5,7) แพตเทิร์นรวมจึงซ้ำที่ ค.ร.น. = 210 รอบย่อย
    # ตาจึงจับ "จุดสังเกต" ได้ยากกว่าใช้ตัวคูณที่หารกันลงตัว
    HARMONICS = (1, -2, 3, -5, 7)

    def __init__(self, loop_seconds: float = 20.0) -> None:
        self.loop_seconds = loop_seconds
        self.wheel = _wheel()
        # ส่วนที่ขึ้นกับตำแหน่งอย่างเดียว คิดครั้งเดียวพอ ประหยัดตอนเบคหลายร้อยเฟรม
        # ความถี่เชิงพื้นที่ต่างกันทุกคลื่น ไม่ให้เกิดก้อนสีใหญ่ก้อนเดียวที่จำง่าย
        self._space = [
            [
                (
                    x * 0.22,
                    y * 0.85 + x * 0.05,
                    (x + y * 3) * 0.13,
                    math.hypot(x - WIDTH * 0.32, (y - HEIGHT / 2) * 4) * 0.14,
                    math.hypot(x - WIDTH * 0.78, (y - HEIGHT / 2) * 4) * 0.11,
                )
                for x in range(WIDTH)
            ]
            for y in range(HEIGHT)
        ]

    def render(self, canvas: Canvas, elapsed: float, frame: int) -> None:
        p = (elapsed / self.loop_seconds) % 1.0
        phases = [TAU * k * p for k in self.HARMONICS]
        pixels = canvas.pixels
        scale = 255.0 / (2.0 * len(phases))
        for y in range(HEIGHT):
            row = self._space[y]
            base = y * WIDTH
            for x in range(WIDTH):
                space = row[x]
                value = 0.0
                for index, phase in enumerate(phases):
                    value += math.sin(space[index] + phase)
                pixels[base + x] = self.wheel[int((value + len(phases)) * scale) & 0xFF]


class ScannerScene(Scene):
    name = "scanner"
    description = "แถบไฟกวาดไปมามีหางจาง วนลูปเนียน"
    fps = 40.0
    loop_seconds = 2.4

    def __init__(self, loop_seconds: float = 2.4, tail: float = 9.0) -> None:
        self.loop_seconds = loop_seconds
        self.tail = tail

    def render(self, canvas: Canvas, elapsed: float, frame: int) -> None:
        p = (elapsed / self.loop_seconds) % 1.0
        # คลื่นสามเหลี่ยม: ไปสุดแล้วกลับ จบที่จุดเริ่มพอดี ลูปจึงต่อเนียน
        head = (1.0 - abs(2.0 * p - 1.0)) * (WIDTH - 1)
        hue = p  # สีวนครบวงล้อพอดีในหนึ่งลูปเช่นกัน
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        for x in range(WIDTH):
            distance = abs(x - head)
            if distance > self.tail:
                continue
            level = (1.0 - distance / self.tail) ** 2
            color = (int(r * 254 * level), int(g * 254 * level), int(b * 254 * level))
            for y in range(HEIGHT):
                # ขอบบน-ล่างหรี่กว่ากลาง ให้ดูเป็นลำแสงมากกว่าแท่งทึบ
                edge = 1.0 if y in (1, 2, 3) else 0.45
                canvas.set(x, y, tuple(int(c * edge) for c in color))  # type: ignore[arg-type]


class BounceScene(Scene):
    name = "bounce"
    description = "ลูกบอลเด้งทิ้งหางสีรุ้ง วนลูปเนียน"
    fps = 40.0
    loop_seconds = 4.0

    def __init__(self, loop_seconds: float = 4.0) -> None:
        self.loop_seconds = loop_seconds
        self.wheel = _wheel()

    def render(self, canvas: Canvas, elapsed: float, frame: int) -> None:
        p = (elapsed / self.loop_seconds) % 1.0
        for index in range(14):  # วาดหางเป็นภาพในอดีตย้อนหลังทีละนิด
            back = index * 0.012
            q = (p - back) % 1.0
            # แกน x ไปกลับ 1 รอบ, แกน y เด้ง 3 รอบ — ทั้งคู่จบพอดีที่ q = 1
            x = (1.0 - abs(2.0 * q - 1.0)) * (WIDTH - 1)
            y = abs(math.sin(TAU * 1.5 * q)) * (HEIGHT - 1)
            level = (1.0 - index / 14.0) ** 2
            color = self.wheel[int(q * 255) & 0xFF]
            canvas.blend(
                int(round(x)), int(round(y)),
                (int(color[0] * level), int(color[1] * level), int(color[2] * level)),
                1.0 if index == 0 else 0.65,
            )
