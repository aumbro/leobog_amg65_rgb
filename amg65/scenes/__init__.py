"""ทะเบียน scene — import แบบขี้เกียจ

scene บางตัวต้องใช้ dependency เสริม (soundcard, winsdk, psutil) ถ้า import
ทุกตัวตั้งแต่ต้น เครื่องที่ขาดของชิ้นเดียวจะใช้ scene อื่นไม่ได้เลย ทะเบียนจึงเก็บแค่
ชื่อโมดูลไว้ แล้วค่อย import ตอนถูกเรียกใช้จริง
"""
from __future__ import annotations

from importlib import import_module

from .base import Scene

# ชื่อ → (โมดูล, คลาส, คำอธิบาย, dependency ที่ต้องมีเพิ่ม)
REGISTRY: dict[str, tuple[str, str, str, str]] = {
    "clock": (".clock", "ClockScene", "นาฬิกา HH:MM:SS + Space Invader", ""),
    "rainbow": (".rainbow", "RainbowScene", "ไล่สีรุ้งไหลทั้งจอ", ""),
    "vis": (".vis", "VisualizerScene", "spectrum เต้นตามเสียงที่ลำโพงกำลังเล่น", "soundcard, numpy"),
    "nowplaying": (".nowplaying", "NowPlayingScene", "ชื่อเพลงวิ่ง + progress bar จาก SMTC", "winsdk"),
    "marquee": (".nowplaying", "MarqueeScene", "ข้อความวิ่งอะไรก็ได้ (--text)", ""),
    "sysmon": (".sysmon", "SysmonScene", "CPU / RAM / เน็ต เป็นบาร์", "psutil"),
    "dino": (".dino", "DinoScene", "เกมไดโนกระโดดข้ามกระบองเพชร (กด space)", ""),
    "pong": (".dino", "PongScene", "ปิงปองเล่นเอง ดูเพลิน ๆ", ""),
}


def load(name: str) -> type[Scene]:
    if name not in REGISTRY:
        raise KeyError(f"ไม่รู้จัก scene {name!r} — มีให้เลือก: {', '.join(REGISTRY)}")
    module_name, class_name, _, extras = REGISTRY[name]
    try:
        module = import_module(module_name, __name__)
    except ImportError as exc:
        raise ImportError(
            f"scene {name!r} ต้องใช้ {extras} — ติดตั้งด้วย pip install {extras.replace(',', '')}\n"
            f"  ({exc})"
        ) from exc
    return getattr(module, class_name)


def describe() -> list[tuple[str, str, str]]:
    return [(name, meta[2], meta[3]) for name, meta in REGISTRY.items()]
