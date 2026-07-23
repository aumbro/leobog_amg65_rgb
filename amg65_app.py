#!/usr/bin/env python
"""จุดเข้าแบบแอป Windows — เปิด tray โดยไม่ต้องมีคอนโซล

ต่างจาก `python -m amg65 tray` ตรงที่ build เป็น .exe แล้วดับเบิลคลิกเปิดได้เลย
และเพราะไม่มีคอนโซล error ที่ปกติ print ออกจอจะหายไป จึงต้อง:
  - เด้ง MessageBox บอกผู้ใช้เมื่อเปิดไม่สำเร็จ (คีย์บอร์ดไม่ต่อ / มีตัวรันอยู่แล้ว)
  - เก็บ log ลงไฟล์ข้าง ๆ ตัวโปรแกรมไว้ดีบัก
"""
from __future__ import annotations

import os
import sys
import traceback


def _log_path() -> str:
    # เขียน log ข้าง exe ตอนแพ็กแล้ว, ข้างสคริปต์ตอนรันสด
    base = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else __file__)
    return os.path.join(base, "amg65.log")


def _message_box(title: str, text: str) -> None:
    """เด้งกล่องข้อความของ Windows — ทางเดียวที่ผู้ใช้เห็น error ตอนไม่มีคอนโซล."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)  # MB_ICONERROR
    except Exception:
        pass


def main() -> int:
    try:
        from amg65.device import AlreadyRunning, claim_exclusive
        from amg65.tray import Tray
    except Exception as exc:  # import พังตั้งแต่ต้น = แพ็กมาไม่ครบ
        _message_box("AMG65 เปิดไม่ได้", f"โหลดโมดูลไม่สำเร็จ:\n{exc}")
        return 1

    try:
        claim_exclusive()  # กันเปิดซ้อน — สองตัวยิง endpoint เดียวกัน = ค้าง
    except AlreadyRunning as exc:
        _message_box("AMG65 เปิดอยู่แล้ว", str(exc))
        return 2

    try:
        return Tray("clock").run()
    except Exception as exc:
        detail = traceback.format_exc()
        try:
            with open(_log_path(), "w", encoding="utf-8") as handle:
                handle.write(detail)
        except OSError:
            pass
        _message_box("AMG65 มีข้อผิดพลาด", f"{type(exc).__name__}: {exc}\n\nดูรายละเอียดใน amg65.log")
        return 1


if __name__ == "__main__":
    sys.exit(main())
