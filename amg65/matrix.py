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

from .device import (
    CMD_APPLY,
    CMD_BEGIN,
    CMD_FINALIZE,
    CMD_STREAM,
    CMD_UPLOAD,
    TRAILER,
    EndpointStalled,
    Link,
)
from . import font

WIDTH = 63
HEIGHT = 5
COUNT = WIDTH * HEIGHT

MAIN_WIDTH = 56   # แผงหลัก x 0–55
RIGHT_WIDTH = 7   # แผงขวา x 56–62

# ค่าช่องสีสูงสุด — โปรโตคอล live stream สงวน 0xFF ไว้ ห้ามส่ง
MAX_CHANNEL = 0xFE

# ไบต์ที่ 2 ของ header ตอนอัปโหลด = ค่าหน่วงต่อเฟรม หน่วยละ 10 ms
# (โปรแกรมทางการใส่ 0x0C = 120 ms = 8.3 FPS มาตลอด ซึ่งไม่ใช่เพดาน)
# วัดจริง: speed 1 -> 12 ms, speed 12 -> 120 ms, แต่ 96 -> 470 ms และ 255 -> 510 ms
# เพราะเฟิร์มแวร์ตัดเพดานหน่วงไว้ราว 500 ms ค่าเกินกว่านั้นจึงไม่ช้าลงอีก
# จับเวลาจริง 4 จุด (10 เฟรมต่อรอบ): speed 1 -> 12 ms, 12 -> 120, 96 -> 470, 255 -> 510
# ฟิตได้ delay = min(10 x speed, 500) + 2   โดย 2 ms คือเวลาสลับเฟรมของเฟิร์มแวร์เอง
FRAME_UNIT_MS = 10.0
FRAME_OVERHEAD_MS = 2.0

# จังหวะระหว่างเฟรมของ live stream — ถอดจากการจับ USB ของโปรแกรมทางการ
# ทางการเว้น 111 ms ต่อเฟรมสม่ำเสมอมาก (104-123) = 9 FPS ทั้งที่ส่ง packet
# ครบเฟรมใช้เวลาแค่ ~53 ms แปลว่ามัน **นั่งเฉย ๆ อีก ~58 ms โดยตั้งใจ**
# ให้เฟิร์มแวร์มีเวลาวาดจอให้เสร็จก่อนรับเฟรมใหม่
# ยิงติด ๆ กันที่ 18.5 FPS (เร็วกว่าทางการ 2 เท่า) ทดสอบแล้วค้างใน 13 วินาที
MIN_FRAME_INTERVAL = 0.111
MAX_FRAME_DELAY_MS = 500.0
SPEED_DEFAULT = 0x0C
FASTEST_FPS = 1000.0 / (FRAME_UNIT_MS + FRAME_OVERHEAD_MS)  # ~83 FPS


def frame_delay_ms(speed: int) -> float:
    return min(speed * FRAME_UNIT_MS, MAX_FRAME_DELAY_MS) + FRAME_OVERHEAD_MS


def speed_for_fps(fps: float) -> int:
    """แปลง FPS ที่อยากได้เป็นค่าไบต์ speed (เร็วสุด ~83 FPS, ช้าสุด ~2 FPS)."""
    if fps <= 0:
        raise ValueError("fps ต้องมากกว่า 0")
    target = min(max(1000.0 / fps - FRAME_OVERHEAD_MS, FRAME_UNIT_MS), MAX_FRAME_DELAY_MS)
    return max(1, min(255, round(target / FRAME_UNIT_MS)))


def fps_for_speed(speed: int) -> float:
    """FPS จริงที่จะได้จากค่าไบต์ speed (คิดเพดานหน่วงและ overhead ให้แล้ว)."""
    return 1000.0 / frame_delay_ms(speed)

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

    delay แยกสองค่าเพราะ 19 packet ในหนึ่งเฟรมทำงานคนละอย่าง:

        command_delay  หลัง 04 18 / 04 35 / flush / 04 02
                       เป็นคำสั่งเปลี่ยนสถานะและ apply ทั้งเฟรม = งานหนักฝั่งเฟิร์มแวร์
        data_delay     ระหว่าง RGB 15 reports
                       แค่ยัดข้อมูลลงบัฟเฟอร์ น่าจะต้องการเวลาน้อยกว่ามาก

    สมมติฐาน: หน่วง 8.5 ms ระหว่างข้อมูล 15 ก้อน = เสียเปล่า 127 ms ต่อเฟรม
    ถ้าจริง ลด data_delay อย่างเดียวจะได้ FPS เพิ่มโดยภาพไม่เสีย

    ⚠️ ส่งถี่เกินไปเครื่องจะ **ทิ้ง report เงียบ ๆ** โดย hid_write ยังคืน 65 ปกติ
    ผลคือข้อมูลที่เหลือเลื่อนไป 64 ไบต์ = 21.3 พิกเซล พิกเซลไปโผล่ผิดตำแหน่ง
    (อาการ "ดอตอื่นโผล่มาบางจังหวะ") โปรแกรมตรวจไม่ได้ ต้องยืนยันด้วยตา
    """

    def __init__(
        self,
        link: Link,
        packet_delay: float = 0.0085,
        header_every_frame: bool = True,
        flush_every_frame: bool = True,
        data_delay: float | None = None,
        command_delay: float | None = None,
        use_ack: bool = True,
        min_frame_interval: float = MIN_FRAME_INTERVAL,
    ) -> None:
        self.link = link
        self.min_frame_interval = min_frame_interval
        self._next_frame_at = 0.0
        # เมื่อ use_ack เปิด (ค่าเริ่มต้น) delay เหล่านี้เป็นแค่ตาข่ายกันตกตอนเครื่องไม่ตอบ
        self.data_delay = packet_delay if data_delay is None else data_delay
        self.command_delay = packet_delay if command_delay is None else command_delay
        self.header_every_frame = header_every_frame
        self.flush_every_frame = flush_every_frame
        self.use_ack = use_ack
        self.acks_missed = 0
        self._stream_ready = False

    @property
    def packet_delay(self) -> float:
        """ค่าที่ช้าที่สุดในสองค่า — ใช้รายงานผลเวลาไม่ได้แยก."""
        return max(self.data_delay, self.command_delay)

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

    def _step(self, payload: bytes | bytearray, fallback_delay: float) -> None:
        """ส่งหนึ่ง report แล้วรอให้เครื่องตอบรับก่อนไปตัวถัดไป

        นี่คือกลไกจริงของโปรโตคอล (ยืนยันจากการจับ USB ของโปรแกรมทางการ):
        เครื่องตอบรับทุก report และผู้ส่งต้องรอคำตอบ = flow control ในตัว
        ถ้าไม่รอ คำตอบจะค้างสะสมในคิว IN จน endpoint ค้าง — ต้นเหตุที่ตามหามาทั้งวัน

        ถ้าไม่ได้คำตอบในเวลา ค่อยถอยไปใช้ delay แบบเดิมเป็นตาข่ายกันตก
        """
        self.link.send(payload)
        if not self.use_ack:
            if fallback_delay > 0:
                time.sleep(fallback_delay)
            return

        if self.link.read_ack():
            return  # เครื่องตอบแล้ว = พร้อมรับตัวต่อไป ไม่ต้องหน่วงเพิ่ม

        # ไม่ตอบในรอบแรก = เครื่องกำลังยุ่ง ให้เวลามันอีกก่อนตัดสิน
        # **ห้ามยิงต่อทันที** — ทดสอบแล้วพบว่าพอ ACK พลาดตัวเดียวแล้วยิงต่อ
        # endpoint ค้างทันทีภายในไม่กี่วินาที เครื่องยังไม่พร้อมแปลว่ายังไม่พร้อมจริง ๆ
        if self.link.read_ack(timeout_ms=250):
            self.acks_missed += 1
            return
        self.acks_missed += 1
        raise EndpointStalled(
            "เครื่องไม่ตอบรับ (ACK) — หยุดส่งเพื่อไม่ให้ endpoint ค้าง\n"
            "  ถ้าเกิดบ่อย ให้ถอดสาย USB เสียบใหม่"
        )

    def enter_stream(self) -> None:
        """เข้าโหมด stream ครั้งเดียว (ใช้ตอน header_every_frame = False)."""
        if self.use_ack:
            self.link.drain()  # ล้าง ACK เก่าค้างคิว ไม่งั้นจังหวะเพี้ยนตั้งแต่ต้น
        self._step(self._begin_payload(), self.command_delay)
        self._step(self._stream_payload(), self.command_delay)
        self._stream_ready = True

    def show(self, canvas: Canvas) -> None:
        self.show_raw(canvas.to_raw_bytes())

    def show_raw(self, raw: bytes | bytearray) -> None:
        if len(raw) != 960:
            raise ValueError("payload ของเฟรมต้องยาว 960 ไบต์")
        # เว้นจังหวะให้เฟิร์มแวร์วาดจอเสร็จก่อน ยิงติดกันเกินไปทำให้ค้าง
        wait = self._next_frame_at - time.perf_counter()
        if wait > 0:
            time.sleep(wait)
        self._next_frame_at = time.perf_counter() + self.min_frame_interval

        try:
            if self.header_every_frame:
                if self.use_ack and not self._stream_ready:
                    # เฟรมแรกของ session: ล้าง ACK ค้างจากรอบก่อน/โปรแกรมอื่น
                    self.link.drain()
                    self._stream_ready = True
                self._step(self._begin_payload(), self.command_delay)
                self._step(self._stream_payload(), self.command_delay)
            elif not self._stream_ready:
                self.enter_stream()
            for offset in range(0, 960, 64):
                self._step(raw[offset : offset + 64], self.data_delay)
            if self.flush_every_frame:
                self._step(bytes(64), self.command_delay)
            self._step(CMD_APPLY, 0.0)
        except OSError:
            # Link retry หมดแล้วยังไม่ผ่าน — ถือว่าหลุดโหมด ต้องเข้าใหม่รอบหน้า
            self._stream_ready = False
            raise

    # ---------- อัปโหลดเป็นชุด (MI_03) ----------

    def upload_animation(
        self,
        bulk: Link,
        frames: list[Canvas],
        speed: int = SPEED_DEFAULT,
        on_progress=None,
        chunk_delay: float = 0.170,
    ) -> None:
        """เก็บภาพ/แอนิเมชันลงเครื่องผ่าน MI_03 — เล่นต่อได้เองแม้ปิดโปรแกรม

        นี่คือทางเดียวที่ได้ภาพลื่นบนจอนี้ เพราะ live stream ตันที่ ~5-6 FPS
        ระหว่างเล่นไม่มีทราฟฟิก USB เลย จึงไม่มีโอกาสที่ endpoint จะค้าง

        `speed` คือไบต์ที่ 2 ของ header ซึ่งโปรแกรมทางการใส่ 0x0C มาตลอด
        ยังไม่ยืนยันว่าคืออะไร — เดาว่าเป็นค่าหน่วงต่อเฟรม เปิดให้ลองค่าอื่นได้
        """
        if not 1 <= len(frames) <= 255:
            raise ValueError("animation ต้องมี 1–255 เฟรม")
        if not 0 <= speed <= 255:
            raise ValueError("speed ต้องอยู่ระหว่าง 0-255")
        payload = bytearray((len(frames), 0, speed, 0))
        for canvas in frames:
            for x, y in RAW_ORDER:
                r, g, b = canvas.pixels[y * WIDTH + x]
                payload.extend((min(r, MAX_CHANNEL), min(g, MAX_CHANNEL), min(b, MAX_CHANNEL)))
        # โปรแกรมทางการใส่ padding หนึ่งไบต์เฉพาะกรณีภาพเดียว
        payload.extend(b"\x00" + TRAILER if len(frames) == 1 else TRAILER)

        init = bytearray(64)
        init[0:2] = CMD_UPLOAD
        init[8] = (len(payload) + 4095) // 4096
        if self.use_ack:
            self.link.drain()
        self._step(self._begin_payload(), self.command_delay)
        self._step(init, self.command_delay)

        chunks = (len(payload) + 4095) // 4096
        for index, offset in enumerate(range(0, len(payload), 4096)):
            bulk.send(payload[offset : offset + 4096])
            if on_progress is not None:
                on_progress(index + 1, chunks)
            # ก้อนใหญ่ 4KB ต้องมีเวลาระบาย โปรแกรมทางการเว้น ~160-167ms
            # ⚠️ ก้อนข้อมูลไปทาง MI_03 แต่คำตอบมาทาง MI_02 (คนละช่อง) จึงอ่าน ACK
            # จาก link ไม่ใช่ bulk — ถ้าได้คำตอบก็ไม่ต้องหน่วงเต็มเวลา
            if self.use_ack and self.link.read_ack(timeout_ms=int(chunk_delay * 1000)):
                continue
            if self.use_ack:
                self.acks_missed += 1
            time.sleep(chunk_delay)
        self._step(CMD_APPLY, self.command_delay)
        self._step(CMD_FINALIZE, 0.0)
