"""วัดสุขภาพการสตรีมของ AMG65 — ACK ครบไหม สตรีมได้นานแค่ไหน

⚠️ เครื่องมือนี้เคยเป็นตัวกวาดหาค่า `--delay` ที่ดีที่สุด ซึ่งเป็น **คำถามที่ผิด**
โปรโตคอลนี้เป็น request/response: เครื่องตอบรับทุก report และต้องรอคำตอบก่อนส่งตัวถัดไป
บวกกับเว้นจังหวะระหว่าง frame 111 ms (ดู §7.4-7.5 ของ AMG65_REVERSE_ENGINEERING.md)
delay ที่เคยไล่จูนกันเป็นเพียงการเดาเพื่อชดเชยกลไกที่ยังไม่รู้จัก

ตอนนี้จึงวัดสิ่งที่มีความหมายจริงแทน:
  - ACK ครบทุก packet ไหม (พลาดแม้ตัวเดียวคือสัญญาณว่ากำลังจะค้าง)
  - สตรีมต่อเนื่องได้นานแค่ไหนก่อน endpoint ค้าง
  - FPS ที่ได้จริง

    python bench_fps.py                    # soak 3 นาที ด้วย plasma
    python bench_fps.py --seconds 600      # ยาว 10 นาที
    python bench_fps.py --scene clock      # scene ที่ข้าม frame ซ้ำได้ = ทราฟฟิกต่ำกว่ามาก
    python bench_fps.py --no-ack           # ปิด ACK เพื่อเทียบว่าต่างกันแค่ไหน
"""
from __future__ import annotations

import argparse
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass

from amg65 import scenes
from amg65.device import DeviceNotFound, EndpointStalled, Link
from amg65.matrix import MIN_FRAME_INTERVAL, Canvas, Matrix

PACKETS_PER_FRAME = 19


def soak(link: Link, scene_name: str, seconds: float, use_ack: bool, interval: float) -> int:
    scene = scenes.load(scene_name)()
    matrix = Matrix(link, use_ack=use_ack, min_frame_interval=interval)
    print(
        f"soak: scene={scene_name} | ACK={'เปิด' if use_ack else 'ปิด'} | "
        f"จังหวะเฟรม {interval * 1000:.0f} ms | นาน {seconds:.0f} วินาที"
    )
    print("(ดูจอไปด้วย — โปรแกรมตรวจ 'dot ผิดตำแหน่ง' ไม่ได้ ต้องใช้ตา)\n")

    scene.start()
    sent = skipped = 0
    last_pixels = None
    started = time.perf_counter()
    stalled_at = None
    mark = 30.0
    try:
        while True:
            elapsed = time.perf_counter() - started
            if elapsed >= seconds:
                break
            canvas = Canvas()
            scene.render(canvas, elapsed, sent + skipped)
            # ข้ามเฟรมซ้ำเหมือนที่ engine ทำจริง ไม่งั้นวัดได้ทราฟฟิกสูงเกินจริง
            if canvas.pixels == last_pixels:
                skipped += 1
                time.sleep(0.01)
                continue
            matrix.show(canvas)
            last_pixels = list(canvas.pixels)
            sent += 1
            if elapsed >= mark:
                print(
                    f"{mark:5.0f} วิ | ส่ง {sent} ข้าม {skipped} | "
                    f"{sent / elapsed:.1f} เฟรม/วิ | ACK พลาด {matrix.acks_missed}"
                )
                mark += 30.0
    except EndpointStalled:
        stalled_at = time.perf_counter() - started
    except KeyboardInterrupt:
        pass
    finally:
        scene.stop()

    duration = time.perf_counter() - started
    print(
        f"\nสรุป: ส่งจริง {sent} เฟรม (ข้าม {skipped}) / {duration:.0f} วินาที"
        f" = {sent / max(duration, 0.01):.1f} เฟรม/วินาที"
    )
    print(f"      packet ที่ส่ง ~{sent * PACKETS_PER_FRAME:,} | ACK พลาด {matrix.acks_missed}")
    if stalled_at is not None:
        print(f"ผล: ✗ endpoint ค้างที่วินาทีที่ {stalled_at:.0f} — ถอดสาย USB เสียบใหม่")
        return 1
    print("ผล: ✓ ไม่ค้างตลอดการทดสอบ")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="วัดสุขภาพการสตรีมของ AMG65")
    parser.add_argument("--scene", default="plasma", choices=tuple(scenes.REGISTRY))
    parser.add_argument("--seconds", type=float, default=180.0)
    parser.add_argument("--no-ack", action="store_true", help="ปิดการรอ ACK (เพื่อเทียบ)")
    parser.add_argument(
        "--frame-interval", type=float, default=MIN_FRAME_INTERVAL * 1000,
        help="จังหวะระหว่างเฟรม (ms) — ค่าจากโปรแกรมทางการคือ 111",
    )
    args = parser.parse_args()

    try:
        with Link("control") as link:
            return soak(
                link, args.scene, args.seconds,
                not args.no_ack, args.frame_interval / 1000.0,
            )
    except EndpointStalled as exc:
        print(f"\n{exc}")
        return 1
    except DeviceNotFound as exc:
        print(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
