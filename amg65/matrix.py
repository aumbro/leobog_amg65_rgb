"""จอ LED Matrix 63×5: ผืนผ้าใบสำหรับวาด + การส่งเฟรมเข้าเครื่อง

**ลำดับ pixel ในหน่วยความจำเครื่องไม่ได้เรียงซ้าย→ขวายาวรวด** (ยืนยันด้วยการถ่ายวิดีโอ
ไล่ทีละจุดครบ 315 จุด) แต่เป็นบล็อก 14×5 แบบ row-major สี่บล็อก แล้วต่อด้วยบล็อกขวา 7×5

    raw   0– 69 → x  0–13   raw 210–279 → x 42–55
    raw  70–139 → x 14–27   raw 280–314 → x 56–62 (แผงขวาที่แยกกายภาพ)
    raw 140–209 → x 28–41

โค้ดที่วาดภาพจึงคิดเป็นพิกัด (x, y) ปกติได้ตลอด แล้วปล่อยให้ `Canvas.to_raw()`
สลับลำดับให้ตอนจะส่งจริง
"""
from __future__ import annotations

import time

from .device import CMD_APPLY, CMD_BEGIN, CMD_FINALIZE, CMD_STREAM, CMD_UPLOAD, TRAILER, Link
from . import font

WIDTH = 63
HEIGHT = 5
COUNT = WIDTH * HEIGHT

MAIN_WIDTH = 56   # แผงหลัก x 0–55
RIGHT_WIDTH = 7   # แผงขวา x 56–62

# ค่าช่องสีสูงสุด — โปรโตคอล live stream สงวน 0xFF ไว้ ห้ามส่ง
MAX_CHANNEL = 0xFE

RGB = tuple[int, int, int]
BLACK: RGB = (0, 0, 0)


def _build_raw_order() -> tuple[tuple[int, int], ...]:
    order: list[tuple[int, int]] = []
    for block in range(4):
        for y in range(HEIGHT):
            for dx in range(14):
                order.append((block * 14 + dx, y))
    for y in range(HEIGHT):
        for x in range(MAIN_WIDTH, WIDTH):
            order.append((x, y))
    return tuple(order)


RAW_ORDER = _build_raw_order()
# แปลง logical index → ตำแหน่งใน buffer ดิบ (ใช้ตอนส่ง จึงคำนวณครั้งเดียวตอน import)
RAW_SLOT = [0] * COUNT
for _slot, (_x, _y) in enumerate(RAW_ORDER):
    RAW_SLOT[_y * WIDTH + _x] = _slot


class Canvas:
    """ผืนผ้าใบ 63×5 คิดพิกัดแบบซ้าย→ขวา บน→ล่าง ตามสามัญสำนึก."""

    __slots__ = ("pixels",)

    def __init__(self) -> None:
        self.pixels: list[RGB] = [BLACK] * COUNT

    def clear(self, color: RGB = BLACK) -> None:
        self.pixels = [color] * COUNT

    def set(self, x: int, y: int, color: RGB) -> None:
        """วาดหนึ่งจุด; นอกขอบจอเงียบ ๆ ไม่ error (scene ส่วนใหญ่วาดล้นขอบเป็นปกติ)."""
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            self.pixels[y * WIDTH + x] = color

    def get(self, x: int, y: int) -> RGB:
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            return self.pixels[y * WIDTH + x]
        return BLACK

    def blend(self, x: int, y: int, color: RGB, alpha: float) -> None:
        """ผสมสีทับของเดิม ใช้ทำหางจาง/เงา."""
        if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
            return
        old = self.pixels[y * WIDTH + x]
        self.pixels[y * WIDTH + x] = (
            int(old[0] + (color[0] - old[0]) * alpha),
            int(old[1] + (color[1] - old[1]) * alpha),
            int(old[2] + (color[2] - old[2]) * alpha),
        )

    def vline(self, x: int, y0: int, y1: int, color: RGB) -> None:
        for y in range(min(y0, y1), max(y0, y1) + 1):
            self.set(x, y, color)

    def hline(self, x0: int, x1: int, y: int, color: RGB) -> None:
        for x in range(min(x0, x1), max(x0, x1) + 1):
            self.set(x, y, color)

    def rect(self, x0: int, y0: int, x1: int, y1: int, color: RGB) -> None:
        for y in range(min(y0, y1), max(y0, y1) + 1):
            for x in range(min(x0, x1), max(x0, x1) + 1):
                self.set(x, y, color)

    def text(
        self,
        text: str,
        x: int,
        color: RGB | None = None,
        y: int = 0,
        tracking: int = font.TRACKING,
        color_of=None,
    ) -> int:
        """วาดข้อความโดยมุมซ้ายบนอยู่ที่ (x, y); คืนความกว้างที่ใช้

        ส่ง `color_of(position, px, py) -> RGB` แทน `color` ได้ ถ้าอยากไล่สีต่อตัวอักษร
        หรือต่อพิกเซล (ใช้ทำนาฬิกาไล่เฉดและข้อความวิ่งสีรุ้ง)
        """
        for dx, dy, position in font.iter_pixels(text, tracking):
            px, py = x + dx, y + dy
            self.set(px, py, color_of(position, px, py) if color_of else (color or BLACK))
        return font.text_width(text, tracking)

    def scale_brightness(self, factor: float) -> None:
        if factor >= 1.0:
            return
        self.pixels = [
            (int(r * factor), int(g * factor), int(b * factor)) for r, g, b in self.pixels
        ]

    def to_raw_bytes(self) -> bytearray:
        """เรียงพิกเซลกลับเป็นลำดับหน่วยความจำเครื่อง แล้วแพ็คเป็น payload 960 ไบต์."""
        raw = bytearray(960)
        offset = 0
        pixels = self.pixels
        for x, y in RAW_ORDER:
            r, g, b = pixels[y * WIDTH + x]
            raw[offset] = r if r < MAX_CHANNEL else MAX_CHANNEL
            raw[offset + 1] = g if g < MAX_CHANNEL else MAX_CHANNEL
            raw[offset + 2] = b if b < MAX_CHANNEL else MAX_CHANNEL
            offset += 3
        raw[945:947] = TRAILER
        return raw


class Matrix:
    """ส่งเฟรมเข้าจอด้วยโปรโตคอลเดียวกับโหมด Music ของโปรแกรมทางการ

    ลำดับต่อหนึ่งเฟรม (ของเดิม 19 reports):
        04 18 → 04 35 (byte 8 = 0F) → RGB 15 reports → zero flush → 04 02

    `header_every_frame` / `flush_every_frame` / `packet_delay` เปิดให้ปรับได้
    เพราะจำนวน report กับ delay คือคอขวด FPS ทั้งหมด — ดู bench_fps.py
    """

    def __init__(
        self,
        link: Link,
        packet_delay: float = 0.0085,
        header_every_frame: bool = True,
        flush_every_frame: bool = True,
    ) -> None:
        self.link = link
        self.packet_delay = packet_delay
        self.header_every_frame = header_every_frame
        self.flush_every_frame = flush_every_frame
        self._stream_ready = False

    # ---------- live stream ----------

    def _begin_payload(self) -> bytearray:
        payload = bytearray(64)
        payload[0:2] = CMD_BEGIN
        return payload

    def _stream_payload(self) -> bytearray:
        payload = bytearray(64)
        payload[0:2] = CMD_STREAM
        payload[8] = 0x0F
        return payload

    def enter_stream(self) -> None:
        """เข้าโหมด stream ครั้งเดียว (ใช้ตอน header_every_frame = False)."""
        self.link.send(self._begin_payload())
        time.sleep(self.packet_delay)
        self.link.send(self._stream_payload())
        time.sleep(self.packet_delay)
        self._stream_ready = True

    def show(self, canvas: Canvas) -> None:
        self.show_raw(canvas.to_raw_bytes())

    def show_raw(self, raw: bytes | bytearray) -> None:
        if len(raw) != 960:
            raise ValueError("payload ของเฟรมต้องยาว 960 ไบต์")
        delay = self.packet_delay
        try:
            if self.header_every_frame:
                self.link.send(self._begin_payload())
                time.sleep(delay)
                self.link.send(self._stream_payload())
                time.sleep(delay)
            elif not self._stream_ready:
                self.enter_stream()
            for offset in range(0, 960, 64):
                self.link.send(raw[offset : offset + 64])
                time.sleep(delay)
            if self.flush_every_frame:
                self.link.send(bytes(64))
                time.sleep(delay)
            self.link.send(CMD_APPLY)
        except OSError:
            # Link retry หมดแล้วยังไม่ผ่าน — ถือว่าหลุดโหมด ต้องเข้าใหม่รอบหน้า
            self._stream_ready = False
            raise

    # ---------- อัปโหลดเป็นชุด (MI_03) ----------

    def upload_animation(self, bulk: Link, frames: list[Canvas]) -> None:
        """เก็บภาพ/แอนิเมชันลงเครื่องผ่าน MI_03 — เล่นต่อได้เองแม้ปิดโปรแกรม

        ต่างจาก live stream ตรงที่ไม่ต้องมี process ค้างไว้ แต่ report ใหญ่ 4097 ไบต์
        และต้องหน่วง ~170ms ต่อก้อน จึงใช้กับภาพนิ่ง/ลูปสั้นเท่านั้น
        """
        if not 1 <= len(frames) <= 255:
            raise ValueError("animation ต้องมี 1–255 เฟรม")
        payload = bytearray((len(frames), 0, 0x0C, 0))
        for canvas in frames:
            for x, y in RAW_ORDER:
                r, g, b = canvas.pixels[y * WIDTH + x]
                payload.extend((min(r, MAX_CHANNEL), min(g, MAX_CHANNEL), min(b, MAX_CHANNEL)))
        # โปรแกรมทางการใส่ padding หนึ่งไบต์เฉพาะกรณีภาพเดียว
        payload.extend(b"\x00" + TRAILER if len(frames) == 1 else TRAILER)

        init = bytearray(64)
        init[0:2] = CMD_UPLOAD
        init[8] = (len(payload) + 4095) // 4096
        self.link.send(self._begin_payload())
        self.link.send(init)
        for offset in range(0, len(payload), 4096):
            bulk.send(payload[offset : offset + 4096])
            time.sleep(0.170)
        self.link.send(CMD_APPLY)
        self.link.send(CMD_FINALIZE)
