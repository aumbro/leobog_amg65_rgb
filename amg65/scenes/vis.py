"""spectrum analyzer เต้นตามเสียงที่ลำโพงกำลังเล่นจริง (WASAPI loopback)

จอสูงแค่ 5 พิกเซล ถ้าปัดเป็นจำนวนเต็มบาร์จะกระตุกเป็นขั้นบันได จึงใช้ *พิกเซลบนสุด
หรี่ตามเศษ* — ได้ความละเอียดเหมือนมี ~50 ขั้นแทนที่จะมี 5 ขั้น

สูตร capture/AGC ยกมาจาก vibe.py (จอ Thermalright Trofeo) ที่จูนกับเครื่องนี้มาแล้ว
"""
from __future__ import annotations

import colorsys
import threading

import numpy as np

from ..matrix import HEIGHT, WIDTH, Canvas
from .base import Scene

SAMPLE_RATE = 48000
FFT_SIZE = 2048
BLOCK = 1024
ATTACK, DECAY = 0.55, 0.16  # ขึ้นเร็ว ตกช้า ดูนุ่มตากว่า
PEAK_DECAY = 1.6            # ความเร็วที่จุด peak ร่วงลง (พิกเซล/วินาที)


class _Spectrum:
    def __init__(self, bands: int) -> None:
        self.lock = threading.Lock()
        self.bands = np.zeros(bands, dtype=np.float32)
        self.n = bands
        self.active = False

    def set(self, values: np.ndarray, active: bool = True) -> None:
        with self.lock:
            self.bands = values
            self.active = active

    def get(self) -> tuple[np.ndarray, bool]:
        with self.lock:
            return self.bands.copy(), self.active


def _band_edges(bands: int, fmin: float = 40.0, fmax: float = 16000.0) -> np.ndarray:
    freqs = np.fft.rfftfreq(FFT_SIZE, 1.0 / SAMPLE_RATE)
    edges = np.geomspace(fmin, min(fmax, SAMPLE_RATE / 2), bands + 1)
    return np.clip(np.searchsorted(freqs, edges), 1, len(freqs) - 1)


def _capture(spec: _Spectrum, stop: threading.Event, gain: float) -> None:
    import warnings

    import soundcard as sc

    # loopback ร้อง "data discontinuity" ทุกครั้งที่เสียงสะดุด — ไม่อันตราย
    warnings.filterwarnings("ignore", message="data discontinuity in recording")

    edges = _band_edges(spec.n)
    window = np.hanning(FFT_SIZE).astype(np.float32)
    ring = np.zeros(FFT_SIZE, dtype=np.float32)
    smoothed = np.zeros(spec.n, dtype=np.float32)
    tilt = np.linspace(1.0, 1.5, spec.n).astype(np.float32)  # ย่านสูงพลังงานน้อย ต้องชดเชย
    agc_ref = 0.5

    # loopback ที่เปิดตอนไม่มีเสียงเล่นอยู่จะส่งแต่ frame ศูนย์ค้างแบบนั้นตลอด
    # (แม้เพลงเริ่มทีหลัง) ต้องเปิด recorder ใหม่ตอนเงียบสนิทนานพอ
    reopen_after = int(SAMPLE_RATE / BLOCK * 2.0)

    def open_recorder():
        speaker = sc.default_speaker()
        mic = sc.get_microphone(str(speaker.name), include_loopback=True)
        return mic.recorder(samplerate=SAMPLE_RATE, channels=2, blocksize=BLOCK)

    silent = 0
    while not stop.is_set():
        try:
            with open_recorder() as recorder:
                while not stop.is_set():
                    data = recorder.record(numframes=BLOCK)
                    if float(np.abs(data).max()) == 0.0:
                        silent += 1
                        if silent >= reopen_after:
                            silent = 0
                            spec.set(np.zeros(spec.n, dtype=np.float32), active=False)
                            break
                    else:
                        silent = 0

                    mono = data.mean(axis=1).astype(np.float32)
                    ring = np.roll(ring, -len(mono))
                    ring[-len(mono) :] = mono

                    power = np.abs(np.fft.rfft(ring * window))
                    raw = np.array(
                        [power[edges[i] : max(edges[i] + 1, edges[i + 1])].mean() for i in range(spec.n)],
                        dtype=np.float32,
                    )
                    pre = np.clip(np.log1p(raw * 5.0) / 5.6, 0.0, 1.0) * tilt

                    # AGC: เพลงเบา/ดังก็ให้ยอดแตะ ~0.85 เท่ากัน (ขึ้นไว ลงช้า)
                    peak = float(pre.max())
                    agc_ref += (peak - agc_ref) * (0.30 if peak > agc_ref else 0.010)
                    auto = min(9.0, max(0.35, 0.85 / max(agc_ref, 0.03)))
                    gate = min(1.0, max(0.0, (peak - 0.03) / 0.06))  # เงียบ → เฟดหาย ไม่บูสต์ noise
                    level = np.clip(pre * auto * gain, 0.0, 1.0) * 0.92 * gate

                    rising = level > smoothed
                    smoothed = np.where(
                        rising,
                        smoothed + (level - smoothed) * ATTACK,
                        smoothed * (1.0 - DECAY) + level * DECAY,
                    )
                    spec.set(smoothed.astype(np.float32), active=True)
        except Exception:
            spec.set(np.zeros(spec.n, dtype=np.float32), active=False)
            stop.wait(2.0)


class VisualizerScene(Scene):
    name = "vis"
    description = "spectrum เต้นตามเสียงที่ลำโพงกำลังเล่น"
    fps = 30.0

    def __init__(self, bands: int = WIDTH, gain: float = 1.0, peaks: bool = True) -> None:
        self.bands = max(1, min(bands, WIDTH))
        self.gain = gain
        self.peaks = peaks
        self.spec = _Spectrum(self.bands)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._peak_level = np.zeros(self.bands, dtype=np.float32)
        self._last_elapsed = 0.0
        # สีตามความถี่: ต่ำ = แดง/ส้ม, กลาง = เขียว, สูง = ฟ้า/ม่วง
        self._hue = [
            colorsys.hsv_to_rgb(0.02 + 0.72 * (i / max(1, self.bands - 1)), 1.0, 1.0)
            for i in range(self.bands)
        ]

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=_capture, args=(self.spec, self._stop, self.gain), daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def render(self, canvas: Canvas, elapsed: float, frame: int) -> None:
        levels, active = self.spec.get()
        delta = max(0.0, elapsed - self._last_elapsed)
        self._last_elapsed = elapsed

        if not active:
            self._idle(canvas, elapsed)
            return

        span = WIDTH / self.bands
        for index, value in enumerate(levels):
            height = float(value) * HEIGHT
            whole = int(height)
            base = self._hue[index]
            x0 = int(index * span)
            x1 = max(x0 + 1, int((index + 1) * span))

            for x in range(x0, x1):
                for step in range(min(whole, HEIGHT)):
                    # จางลงเมื่อสูงขึ้น ทำให้ฐานบาร์ดูหนักแน่นและยอดดูเบา
                    shade = 0.55 + 0.45 * (1.0 - step / HEIGHT)
                    canvas.set(
                        x, HEIGHT - 1 - step,
                        (int(base[0] * 254 * shade), int(base[1] * 254 * shade), int(base[2] * 254 * shade)),
                    )
                if whole < HEIGHT:
                    frac = height - whole
                    canvas.set(
                        x, HEIGHT - 1 - whole,
                        (int(base[0] * 254 * frac), int(base[1] * 254 * frac), int(base[2] * 254 * frac)),
                    )

            if self.peaks:
                self._peak_level[index] = max(
                    float(value) * HEIGHT, self._peak_level[index] - PEAK_DECAY * delta
                )
                peak_y = HEIGHT - 1 - int(min(self._peak_level[index], HEIGHT - 1))
                for x in range(x0, x1):
                    canvas.blend(x, peak_y, (254, 254, 254), 0.75)

    @staticmethod
    def _idle(canvas: Canvas, elapsed: float) -> None:
        """ไม่มีเสียงเล่นอยู่ — คลื่นจาง ๆ วิ่งไปมาให้รู้ว่ายังทำงานอยู่."""
        head = (elapsed * 18.0) % (WIDTH * 2)
        head = head if head < WIDTH else WIDTH * 2 - head
        for x in range(WIDTH):
            distance = abs(x - head)
            if distance < 8:
                value = int(90 * (1.0 - distance / 8.0))
                canvas.set(x, HEIGHT - 1, (value // 3, value // 2, value))
