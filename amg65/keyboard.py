"""ไฟใต้ปุ่มคีย์บอร์ด: เอฟเฟกต์สำเร็จรูปของเฟิร์มแวร์ + กำหนดสีรายปุ่ม

ลำดับ transaction ถอดจาก DeviceDriver.exe 1.0.3.2:
    04 18 (เริ่ม) → 04 13 (byte 8 = 01, เตรียม) → ข้อมูล 64 ไบต์ → 04 02 (apply) → 04 F0
"""
from __future__ import annotations

import random
import time

from .device import CMD_APPLY, CMD_BEGIN, CMD_EFFECT, CMD_FINALIZE, CMD_PER_KEY, TRAILER, Link

COMMAND_DELAY = 0.200

# จังหวะระหว่างรอบของไฟรายปุ่มตอน --hold (live preview ต้องส่งซ้ำไม่งั้นไฟดับ)
# ใช้ค่าเดียวกับ matrix เพราะเป็น endpoint เดียวกัน (MI_02) และเจอปัญหาแบบเดียวกัน
# ยิงรัวติดกัน = คำตอบค้างคิว = endpoint ค้าง
MIN_ROUND_INTERVAL = 0.111

MODES = {
    "off": 0, "static": 1, "single-on": 2, "single-off": 3, "glittering": 4,
    "falling": 5, "colourful": 6, "breath": 7, "spectrum": 8, "outward": 9,
    "scrolling": 10, "rolling": 11, "rotating": 12, "explode": 13, "launch": 14,
    "ripples": 15, "flowing": 16, "pulsating": 17, "tilt": 18, "shuttle": 19,
}

# light_index จาก KeyboardLayout.xml ของ AMG65 (เลย์เอาต์ 67 ปุ่ม)
KEY_INDEX = {
    "esc": 0,
    "1": 17, "2": 18, "3": 19, "4": 20, "5": 21, "6": 22,
    "7": 23, "8": 24, "9": 25, "0": 26, "minus": 27, "equal": 28,
    "backspace": 92, "home": 104, "volup": 13, "voldown": 14,
    "tab": 32, "q": 33, "w": 34, "e": 35, "r": 36, "t": 37,
    "y": 38, "u": 39, "i": 40, "o": 41, "p": 42,
    "lbracket": 43, "rbracket": 44, "backslash": 60, "delete": 106,
    "capslock": 48, "a": 49, "s": 50, "d": 51, "f": 52, "g": 53,
    "h": 54, "j": 55, "k": 56, "l": 57, "semicolon": 58, "quote": 59,
    "enter": 76, "pageup": 105,
    "lshift": 64, "z": 65, "x": 66, "c": 67, "v": 68, "b": 69,
    "n": 70, "m": 71, "comma": 72, "dot": 73, "slash": 74,
    "rshift": 75, "up": 90, "pagedown": 108,
    "lctrl": 80, "lwin": 81, "lalt": 82, "space": 83, "fn": 85,
    "rctrl": 87, "left": 88, "down": 89, "right": 91,
}

# ลำดับ tuple ที่ capture ได้ตอนโปรแกรมทางการอัปโหลด Custom Light
# ตำแหน่งในตาราง *ไม่ใช่* light_index × 4 แต่เรียงตามลำดับนี้
LIGHT_ORDER = (
    [0] + list(range(17, 29)) + [92, 104, 13, 14]
    + list(range(32, 45)) + [60, 106]
    + list(range(48, 60)) + [76, 105]
    + list(range(64, 76)) + [90, 108]
    + [80, 81, 82, 83, 85, 87, 88, 89, 91]
)


class KeyboardLight:
    def __init__(self, link: Link, use_ack: bool = True) -> None:
        self.link = link
        self.use_ack = use_ack
        self.acks_missed = 0

    def _step(self, payload: bytes | bytearray, delay: float = COMMAND_DELAY) -> None:
        """ส่งหนึ่ง report แล้วรอให้เครื่องตอบรับ

        ช่องนี้เป็น endpoint เดียวกับ matrix (MI_02) จึงใช้กลไก request/response
        เหมือนกัน — เครื่องตอบรับทุก report และต้องรอก่อนส่งตัวถัดไป
        ถ้าไม่รอแล้วยิงรัว (โดยเฉพาะ `keys --hold` ที่เป็น live stream เหมือนกัน)
        คำตอบจะค้างสะสมในคิวจน endpoint ค้าง — ปัญหาเดียวกับที่แก้ไปใน matrix.py

        delay ที่ส่งเข้ามาเป็นแค่ตาข่ายกันตกตอนเครื่องไม่ตอบ
        """
        self.link.send(payload)
        if self.use_ack:
            if self.link.read_ack():
                return
            self.acks_missed += 1
        if delay > 0:
            time.sleep(delay)

    def set_effect(
        self,
        mode: int,
        rgb: tuple[int, int, int] = (255, 255, 255),
        brightness: int = 5,
        speed: int = 3,
        direction: int = 0,
        colorful: bool = False,
    ) -> None:
        self._step(CMD_BEGIN)

        init = bytearray(64)
        init[0:2] = CMD_EFFECT
        init[8] = 1
        self._step(init)

        data = bytearray(64)
        data[0] = mode
        if mode:
            data[1:4] = bytes(rgb)
            data[8] = int(colorful)
            data[9] = brightness
            data[10] = speed
            data[11] = direction
        data[14:16] = TRAILER
        self._step(data)

        self._step(CMD_APPLY)
        self._step(CMD_FINALIZE)

    def _write_table(self, table: bytearray, init: bytearray, stream_delay: float) -> None:
        """ส่งตารางสี 512 ไบต์หนึ่งรอบ (init + 8 ก้อน)."""
        self._step(init, stream_delay)
        for offset in range(0, len(table), 64):
            self._step(table[offset : offset + 64], stream_delay)

    @staticmethod
    def _fill_table(table: bytearray, colors: dict[str, tuple[int, int, int]]) -> None:
        by_index = {KEY_INDEX[key]: rgb for key, rgb in colors.items() if key in KEY_INDEX}
        for slot, index in enumerate(LIGHT_ORDER):
            r, g, b = by_index.get(index, (0, 0, 0))
            table[slot * 4 : slot * 4 + 4] = bytes((index, r, g, b))

    def stream_effect(self, effect, fps: float = 9.0, stream_delay: float = 0.025) -> None:
        """สตรีมเอฟเฟกต์ไฟใต้ปุ่มต่อเนื่องจนกด Ctrl+C

        `effect` ต้องมี start() / stop() / colors(elapsed) -> {ชื่อปุ่ม: (r,g,b)}
        (ดู amg65/keyfx.py)

        จังหวะระหว่างรอบใช้หลักเดียวกับ matrix — ยิงติดกันเกินไปทำให้ endpoint ค้าง
        รอบหนึ่งมี 9 packet (init + 8) ซึ่งน้อยกว่า matrix (19) จึงเร็วกว่าได้
        """
        table = bytearray(0x200)
        init = bytearray(64)
        init[0:2] = CMD_PER_KEY
        init[8] = 0x08

        interval = 1.0 / max(fps, 0.5)
        # เริ่มเอฟเฟกต์ก่อน (บางตัวเปิด thread จับเสียง ใช้เวลาตั้งตัว) แล้วค่อยล้างคิว
        # ให้ชิดกับการส่งจริงที่สุด — ถ้าล้างแล้วปล่อยว่างนาน มีอะไรเข้าคิวมาก็เสียจังหวะ
        effect.start()
        if self.use_ack:
            self.link.drain()
        started = time.perf_counter()
        try:
            while True:
                loop_start = time.perf_counter()
                self._fill_table(table, effect.colors(loop_start - started))
                self._write_table(table, init, stream_delay)
                remaining = interval - (time.perf_counter() - loop_start)
                if remaining > 0:
                    time.sleep(remaining)
        finally:
            effect.stop()

    def set_per_key(
        self,
        colors: dict[str, tuple[int, int, int]],
        hold: bool = False,
        randomize: bool = False,
        stream_delay: float = 0.025,
    ) -> None:
        """ระบายสีรายปุ่ม ปุ่มที่ไม่ได้ระบุจะดับ

        04 20 เป็น live preview เฟิร์มแวร์ดับไฟเองเมื่อข้อมูลหยุดมา จึงต้อง hold ไว้
        ถ้าอยากให้ค้าง — ตรงนี้เลียนแบบพฤติกรรมโปรแกรมทางการ
        """
        by_index = {KEY_INDEX[key]: rgb for key, rgb in colors.items()}
        table = bytearray(0x200)  # 128 ช่องเรียงกัน ใช้จริง 67 ช่อง
        for slot, index in enumerate(LIGHT_ORDER):
            r, g, b = by_index.get(index, (0, 0, 0))
            table[slot * 4 : slot * 4 + 4] = bytes((index, r, g, b))

        init = bytearray(64)
        init[0:2] = CMD_PER_KEY
        init[8] = 0x08

        if self.use_ack:
            self.link.drain()  # ล้าง ACK เก่าค้างคิวก่อนเริ่ม ไม่งั้นจังหวะเพี้ยน

        next_round = 0.0
        while True:  # noqa: PLR1702
            # เว้นจังหวะระหว่างรอบเหมือน matrix — ยิงรัวติดกันทำให้ endpoint ค้าง
            wait = next_round - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
            next_round = time.perf_counter() + MIN_ROUND_INTERVAL

            if randomize:
                for slot, index in enumerate(LIGHT_ORDER):
                    table[slot * 4 : slot * 4 + 4] = bytes(
                        (index, *(random.randint(48, 255) for _ in range(3)))
                    )
            self._step(init, stream_delay)
            for offset in range(0, len(table), 64):
                self._step(table[offset : offset + 64], stream_delay)
            if not hold:
                return
