"""ข้อความวิ่ง และ now-playing จาก SMTC ของ Windows

`MarqueeScene` วิ่งข้อความอะไรก็ได้
`NowPlayingScene` ดึงชื่อเพลงจาก SMTC (System Media Transport Controls) จึงได้เพลง
จากทุกแอปที่คุมด้วยปุ่ม media ได้ — Spotify / YouTube / Apple Music ไม่ต้องต่อ API ใคร

การจัดพื้นที่ 63×5:
    x 0–55  ข้อความวิ่ง "ชื่อเพลง - ศิลปิน"  (แถวล่างมีขีดความคืบหน้าจาง ๆ ซ้อนอยู่)
    x 56–62 ไอคอนเล่น/หยุด บนแผงขวาที่แยกกายภาพ
"""
from __future__ import annotations

import colorsys
import threading
import time

from .. import font
from ..matrix import MAIN_WIDTH, WIDTH, Canvas
from .base import Scene

GAP = 6  # ช่องว่างระหว่างข้อความรอบเก่ากับรอบใหม่ตอนวนซ้ำ


class MarqueeScene(Scene):
    name = "marquee"
    description = "ข้อความวิ่งอะไรก็ได้"
    fps = 20.0

    def __init__(self, text: str = "AMG65", speed: float = 14.0, rainbow: bool = True) -> None:
        self.text = text
        self.speed = speed  # พิกเซลต่อวินาที
        self.rainbow = rainbow

    def _color_of(self, now: float):
        if not self.rainbow:
            return lambda _position, _px, _py: (254, 254, 254)

        def color_of(_position: int, px: int, _py: int) -> tuple[int, int, int]:
            r, g, b = colorsys.hsv_to_rgb((px / 40.0 + now * 0.15) % 1.0, 0.85, 1.0)
            return int(r * 254), int(g * 254), int(b * 254)

        return color_of

    def draw_scrolling(
        self, canvas: Canvas, text: str, elapsed: float, x0: int = 0, x1: int = WIDTH
    ) -> None:
        """วาดข้อความวิ่งในช่วง x0–x1; ถ้าข้อความสั้นกว่าช่องก็จัดกลางแล้วอยู่นิ่ง."""
        width = font.text_width(text)
        span = x1 - x0
        color_of = self._color_of(elapsed)
        if width <= span:
            canvas.text(text, x0 + (span - width) // 2, color_of=color_of)
            return
        period = width + GAP
        offset = (elapsed * self.speed) % period
        # วาดสองรอบเหลื่อมกัน ข้อความจึงต่อเนื่องไม่มีช่วงจอว่าง
        for repeat in (0, 1):
            start = x0 - int(offset) + repeat * period
            if start > x1 or start + width < x0:
                continue
            for dx, dy, position in font.iter_pixels(text):
                px = start + dx
                if x0 <= px < x1:
                    canvas.set(px, dy, color_of(position, px, dy))

    def render(self, canvas: Canvas, elapsed: float, frame: int) -> None:
        self.draw_scrolling(canvas, self.text, elapsed)


class _MediaState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.title = ""
        self.artist = ""
        self.playing = False
        self.position = 0.0
        self.duration = 0.0
        self.stamp = 0.0

    def update(self, title, artist, playing, position, duration) -> None:
        with self.lock:
            self.title, self.artist = title, artist
            self.playing, self.position, self.duration = playing, position, duration
            self.stamp = time.perf_counter()

    def snapshot(self):
        with self.lock:
            position = self.position
            # SMTC อัปเดตตำแหน่งช้ากว่าเฟรม เดินนาฬิกาต่อเองระหว่างรอบเพื่อให้บาร์ลื่น
            if self.playing and self.stamp:
                position += time.perf_counter() - self.stamp
            return self.title, self.artist, self.playing, position, self.duration


def _smtc_worker(state: _MediaState, stop: threading.Event) -> None:
    import asyncio

    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager,
    )

    async def once(manager) -> None:
        session = manager.get_current_session()
        if session is None:
            state.update("", "", False, 0.0, 0.0)
            return
        props = await session.try_get_media_properties_async()
        timeline = session.get_timeline_properties()
        playback = session.get_playback_info()
        state.update(
            props.title or "",
            props.artist or props.album_artist or "",
            int(playback.playback_status) == 4,  # 4 = Playing
            timeline.position.total_seconds() if timeline.position else 0.0,
            timeline.end_time.total_seconds() if timeline.end_time else 0.0,
        )

    async def run() -> None:
        manager = await Manager.request_async()
        while not stop.is_set():
            try:
                await once(manager)
            except Exception:
                pass  # แอปเพลงปิดกลางคัน / session หลุด — รอบหน้าค่อยว่ากัน
            await asyncio.sleep(0.5)

    try:
        asyncio.run(run())
    except Exception:
        pass


class NowPlayingScene(MarqueeScene):
    name = "nowplaying"
    description = "ชื่อเพลงวิ่ง + ความคืบหน้า จาก SMTC"
    fps = 20.0

    def __init__(self, speed: float = 14.0) -> None:
        super().__init__("", speed, rainbow=True)
        self.state = _MediaState()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=_smtc_worker, args=(self.state, self._stop), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def render(self, canvas: Canvas, elapsed: float, frame: int) -> None:
        title, artist, playing, position, duration = self.state.snapshot()
        label = " - ".join(part for part in (title, artist) if part) or "NO MUSIC"
        self.draw_scrolling(canvas, label, elapsed, 0, MAIN_WIDTH)

        # ขีดความคืบหน้าจาง ๆ ที่แถวล่าง วาดทับเฉพาะจุดที่ตัวอักษรไม่ได้ใช้
        if duration > 0:
            progress = max(0.0, min(1.0, position / duration))
            for x in range(int(progress * MAIN_WIDTH)):
                if canvas.get(x, 4) == (0, 0, 0):
                    canvas.set(x, 4, (40, 40, 46))

        self._draw_transport(canvas, playing, elapsed)

    @staticmethod
    def _draw_transport(canvas: Canvas, playing: bool, elapsed: float) -> None:
        """แผงขวา: สามเหลี่ยมเล่น (เขียว) หรือสองขีดหยุด (ส้ม) พร้อมหายใจเบา ๆ."""
        level = 0.55 + 0.45 * abs(((elapsed * 0.6) % 2.0) - 1.0)
        if playing:
            color = (int(0 * level), int(230 * level), int(90 * level))
            shape = ("1000000", "1110000", "1111100", "1110000", "1000000")
        else:
            color = (int(254 * level), int(150 * level), 0)
            shape = ("0110110", "0110110", "0110110", "0110110", "0110110")
        for y, row in enumerate(shape):
            for dx, bit in enumerate(row):
                if bit == "1":
                    canvas.set(MAIN_WIDTH + dx, y, color)
