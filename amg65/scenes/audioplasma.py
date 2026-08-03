"""plasma ที่สีและความเคลื่อนไหวเต้นตามเพลง

ต่อยอดจาก PlasmaScene (คลื่นสีไหลนุ่ม) โดยเอาระดับเสียงจาก WASAPI loopback มาขับ:
    เบส (ย่านต่ำ)  -> ดันความสว่าง + เร่งคลื่นให้ไหลเร็วขึ้นตอนบีตมา
    เสียงรวม       -> เลื่อน hue ทั้งภาพ (เพลงดัง = สีสด/เปลี่ยนไว, เงียบ = ซีดลง)

ยืม _Spectrum/_capture จาก scenes/vis.py (จูนกับเครื่องนี้แล้ว) จึงไม่ต้องเขียน
ท่อจับเสียงใหม่ ต่างจาก vis ตรงที่ไม่ได้โชว์เป็นบาร์ แต่เอาพลังงานเสียงมาปรุงคลื่น
"""
from __future__ import annotations

import colorsys
import math
import threading

import numpy as np

from ..matrix import HEIGHT, WIDTH, Canvas
from .base import Scene

TAU = math.tau


class AudioPlasmaScene(Scene):
    name = "audioplasma"
    description = "plasma ที่สีและความเร็วเต้นตามเพลง"
    fps = 30.0

    def __init__(self, bands: int = 24, gain: float = 1.0) -> None:
        from .vis import _Spectrum

        self.bands = bands
        self.gain = gain
        self.spec = _Spectrum(bands)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.wheel = [
            tuple(int(c * 254) for c in colorsys.hsv_to_rgb(i / 256.0, 1.0, 1.0))
            for i in range(256)
        ]
        # ความถี่เชิงพื้นที่ของแต่ละคลื่น คิดครั้งเดียว (แพงถ้าคูณทุกเฟรม)
        self._space = [
            [
                (x * 0.22, y * 0.85 + x * 0.05, (x + y * 3) * 0.13,
                 math.hypot(x - WIDTH * 0.5, (y - HEIGHT / 2) * 4) * 0.13)
                for x in range(WIDTH)
            ]
            for y in range(HEIGHT)
        ]
        self._phase = 0.0          # เฟสคลื่นที่สะสม (เร่งตามเบส)
        self._energy = 0.0         # พลังงานเสียงเรียบ ๆ (ขับ hue/ความสว่าง)
        self._last_elapsed = 0.0

    def start(self) -> None:
        from .vis import _capture

        self._stop.clear()
        self._thread = threading.Thread(
            target=_capture, args=(self.spec, self._stop, self.gain), daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def render(self, canvas: Canvas, elapsed: float, frame: int) -> None:
        dt = max(0.0, min(0.1, elapsed - self._last_elapsed))
        self._last_elapsed = elapsed

        levels, active = self.spec.get()
        if active and len(levels):
            bass = float(np.mean(levels[: max(1, self.bands // 4)]))   # ย่านต่ำ
            overall = float(np.mean(levels))
        else:
            bass = overall = 0.0

        # พลังงานตามเสียงแบบเรียบ (ขึ้นไว ลงช้า) กันกระตุก — ทำให้ลื่นขึ้นด้วยการลง
        # ช้ากว่าเดิม ไม่ให้สีวูบดับเร็วเกินตอนจังหวะเบา
        self._energy += (overall - self._energy) * (0.35 if overall > self._energy else 0.05)
        # คลื่นไหลช้า ๆ — ฐาน 0.09 รอบ/วิ (คลื่นครบรอบทุก ~11 วิ) เบสเร่งเบา ๆ
        self._phase += dt * (0.09 + bass * 0.6) * TAU

        # สีค่อย ๆ เลื่อนช้ามาก ให้เฉดไหลนุ่ม ไม่กระโดด
        hue_shift = self._energy * 0.12
        brightness = 0.4 + 0.6 * min(1.0, self._energy * 1.6)

        p = self._phase
        pixels = canvas.pixels
        for y in range(HEIGHT):
            row = self._space[y]
            base = y * WIDTH
            for x in range(WIDTH):
                a, b, c, d = row[x]
                value = (
                    math.sin(a + p)
                    + math.sin(b + p * 1.7)
                    + math.sin(c - p * 1.3)
                    + math.sin(d - p * 0.6)
                )
                index = int(((value * 0.125 + 0.5) + hue_shift) * 255) & 0xFF
                r, g, b_ = self.wheel[index]
                pixels[base + x] = (
                    int(r * brightness), int(g * brightness), int(b_ * brightness)
                )
