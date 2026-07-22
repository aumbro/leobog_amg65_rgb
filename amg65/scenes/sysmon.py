"""มอนิเตอร์เครื่อง: CPU / RAM / เน็ต เป็นบาร์ + ตัวเลข CPU% บนแผงขวา

layout (แผงหลัก 56 คอลัมน์ แถวละหนึ่งตัวชี้วัด):
    แถว 0  CPU รวม        เขียว → เหลือง → แดง ตามโหลด
    แถว 1  RAM ที่ใช้      ฟ้า → ม่วง
    แถว 2  เน็ตขาลง        สเกล log 1KB/s – 100MB/s
    แถว 3  เน็ตขาขึ้น
    แถว 4  CPU รายคอร์     แบ่ง 56 px ตามจำนวนคอร์
แผงขวา 7×5 = CPU% สองหลัก (3+1+3 = 7 พอดี)
"""
from __future__ import annotations

import math
import time

import psutil

from ..matrix import MAIN_WIDTH, WIDTH, Canvas
from .base import Scene

BAR_WIDTH = MAIN_WIDTH
NET_FLOOR = 1_000.0        # 1 KB/s = บาร์เริ่มติด
NET_CEILING = 100_000_000.0  # 100 MB/s = บาร์เต็ม


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def _load_color(ratio: float) -> tuple[int, int, int]:
    """เขียว→เหลือง→แดง; ครึ่งล่างกับครึ่งบนไล่คนละช่วงเพื่อให้เห็นความต่างชัด."""
    if ratio < 0.5:
        return _lerp((0, 254, 40), (254, 220, 0), ratio * 2)
    return _lerp((254, 220, 0), (254, 0, 0), (ratio - 0.5) * 2)


class SysmonScene(Scene):
    name = "sysmon"
    description = "CPU / RAM / เน็ต เป็นบาร์"
    fps = 10.0

    def __init__(self) -> None:
        self._last_net = None
        self._last_time = 0.0
        self._down = 0.0
        self._up = 0.0

    def start(self) -> None:
        psutil.cpu_percent(percpu=True)  # เรียกครั้งแรกได้ 0 เสมอ ทิ้งไป
        counters = psutil.net_io_counters()
        self._last_net = (counters.bytes_recv, counters.bytes_sent)
        self._last_time = time.perf_counter()

    def _sample_net(self) -> tuple[float, float]:
        now = time.perf_counter()
        counters = psutil.net_io_counters()
        gap = now - self._last_time
        if self._last_net is None or gap < 0.20:
            return self._down, self._up
        recv, sent = counters.bytes_recv, counters.bytes_sent
        self._down = max(0.0, (recv - self._last_net[0]) / gap)
        self._up = max(0.0, (sent - self._last_net[1]) / gap)
        self._last_net = (recv, sent)
        self._last_time = now
        return self._down, self._up

    def _bar(self, canvas: Canvas, y: int, ratio: float, color: tuple[int, int, int]) -> None:
        filled = ratio * BAR_WIDTH
        whole = int(filled)
        for x in range(min(whole, BAR_WIDTH)):
            canvas.set(x, y, color)
        # พิกเซลสุดท้ายหรี่ตามเศษ ทำให้บาร์ขยับนุ่มขึ้นทั้งที่มีแค่ 56 ขั้น
        if whole < BAR_WIDTH:
            canvas.set(whole, y, _lerp((0, 0, 0), color, filled - whole))

    @staticmethod
    def _net_ratio(rate: float) -> float:
        if rate <= NET_FLOOR:
            return 0.0
        return min(1.0, math.log10(rate / NET_FLOOR) / math.log10(NET_CEILING / NET_FLOOR))

    def render(self, canvas: Canvas, elapsed: float, frame: int) -> None:
        per_core = psutil.cpu_percent(percpu=True)
        cpu = sum(per_core) / len(per_core) if per_core else 0.0
        ram = psutil.virtual_memory().percent
        down, up = self._sample_net()

        self._bar(canvas, 0, cpu / 100.0, _load_color(cpu / 100.0))
        self._bar(canvas, 1, ram / 100.0, _lerp((0, 120, 254), (254, 0, 200), ram / 100.0))
        self._bar(canvas, 2, self._net_ratio(down), (0, 200, 254))
        self._bar(canvas, 3, self._net_ratio(up), (254, 140, 0))

        # แถวล่าง: หนึ่งช่วงต่อหนึ่งคอร์ เว้นหนึ่งพิกเซลคั่นให้นับคอร์ได้
        if per_core:
            span = BAR_WIDTH // len(per_core)
            for index, value in enumerate(per_core):
                x0 = index * span
                lit = int(round(value / 100.0 * (span - 1)))
                for dx in range(max(lit, 1) if value > 3 else 0):
                    canvas.set(x0 + dx, 4, _load_color(value / 100.0))

        # แผงขวา: CPU% สองหลัก (100% แสดงเป็น 99 เพราะมีที่แค่สองหลัก)
        digits = f"{min(int(round(cpu)), 99):02d}"
        canvas.text(digits, MAIN_WIDTH, _load_color(cpu / 100.0))
