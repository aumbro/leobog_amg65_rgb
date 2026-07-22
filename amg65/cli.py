"""หน้าบ้านบรรทัดคำสั่งของ amg65"""
from __future__ import annotations

import argparse
import sys
import time

from . import scenes
from .device import CONTROL_REPORT_BYTES, DeviceNotFound, Link, find_path
from .engine import Engine, MatrixSink, MultiSink, PreviewSink
from .keyboard import KEY_INDEX, MODES, KeyboardLight
from .matrix import Matrix

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass


def byte_value(text: str) -> int:
    value = int(text)
    if not 0 <= value <= 255:
        raise argparse.ArgumentTypeError("ต้องอยู่ระหว่าง 0-255")
    return value


def level_value(text: str) -> int:
    value = int(text)
    if not 0 <= value <= 5:
        raise argparse.ArgumentTypeError("ต้องอยู่ระหว่าง 0-5")
    return value


def cmd_list(_args: argparse.Namespace) -> int:
    print(f"{'scene':<12} {'ต้องมีเพิ่ม':<18} คำอธิบาย")
    print("-" * 72)
    for name, description, extras in scenes.describe():
        print(f"{name:<12} {extras or '-':<18} {description}")
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    """ตรวจว่าคีย์บอร์ดพร้อมรับคำสั่งไหม — MI_02 ค้างเป็นอาการที่เจอบ่อยที่สุด"""
    import hid

    print("อุปกรณ์ที่เจอ (VID 0C45 / PID 800A):")
    found = False
    for item in hid.enumerate(0x0C45, 0x800A):
        found = True
        print(
            f"  MI_0{item.get('interface_number')} "
            f"usage page 0x{item.get('usage_page', 0):04X}  {item.get('product_string')}"
        )
    if not found:
        print("  ไม่เจอเลย — ต่อสาย USB และสลับสวิตช์มาโหมดมีสาย")
        return 1

    ok = True
    for channel, label in (("control", "MI_02 คุมไฟ/stream"), ("bulk", "MI_03 อัปโหลด")):
        try:
            path = find_path(channel)
        except DeviceNotFound as exc:
            print(f"\n{label}: ไม่เจอ endpoint\n{exc}")
            ok = False
            continue
        dev = hid.device()
        dev.open_path(path)
        report = bytearray(CONTROL_REPORT_BYTES if channel == "control" else 4097)
        report[1:3] = b"\x04\x18"
        started = time.perf_counter()
        try:
            written = dev.write(bytes(report))
        except OSError as exc:
            written = -1
            print(f"  ({exc})")
        took = time.perf_counter() - started
        dev.close()
        if written == len(report):
            print(f"\n{label}: ปกติ  (เขียน {written} ไบต์ / {took * 1000:.0f} ms)")
        else:
            ok = False
            print(f"\n{label}: ค้าง!  (เขียนได้ {written} / {took * 1000:.0f} ms)")
            print("  endpoint ค้าง มักเกิดจาก stream ถูกฆ่ากลางเฟรม")
            print("  วิธีแก้: ถอดสาย USB เสียบใหม่ แล้วรัน doctor ซ้ำ")
    return 0 if ok else 1


def cmd_show(args: argparse.Namespace) -> int:
    try:
        scene_class = scenes.load(args.scene)
    except (KeyError, ImportError) as exc:
        print(exc)
        return 2

    kwargs = {}
    if args.scene == "marquee":
        kwargs["text"] = args.text or "AMG65"
    scene = scene_class(**kwargs)

    sinks = []
    link = None
    if not args.no_device:
        try:
            link = Link("control")
            link.open()
            matrix = Matrix(
                link,
                packet_delay=args.delay / 1000.0,
                header_every_frame=not args.lean,
                flush_every_frame=not args.lean,
            )
            sinks.append(MatrixSink(matrix))
        except (OSError, DeviceNotFound) as exc:
            print(f"เปิดคีย์บอร์ดไม่ได้: {exc}\nรันต่อด้วย --preview อย่างเดียว\n")
            args.preview = True
    if args.preview or not sinks:
        sinks.append(PreviewSink())

    sink = sinks[0] if len(sinks) == 1 else MultiSink(*sinks)
    engine = Engine(sink, fps=args.fps)
    try:
        engine.run(scene, duration=args.seconds)
    except KeyboardInterrupt:
        pass
    finally:
        sink.close()
        if link is not None:
            link.close()
    dropped = getattr(sink, "drops", 0)
    print(f"\nจบ — FPS จริงล่าสุด {engine.actual_fps:.1f}" + (f", เฟรมหลุด {dropped}" if dropped else ""))
    return 0


def cmd_light(args: argparse.Namespace) -> int:
    with Link("control", dry_run=args.dry_run) as link:
        KeyboardLight(link).set_effect(
            MODES[args.effect], tuple(args.rgb), args.brightness,
            args.speed, args.direction, args.colorful,
        )
    print("ตั้งค่าไฟสำเร็จ")
    return 0


def cmd_keys(args: argparse.Namespace) -> int:
    import random

    if args.random:
        colors = {k: tuple(random.randint(48, 255) for _ in range(3)) for k in KEY_INDEX}
    else:
        if not args.key:
            print("ต้องมี --key อย่างน้อยหนึ่งรายการ หรือใช้ --random")
            return 2
        colors = {}
        for key, r, g, b in args.key:
            key = key.lower()
            if key not in KEY_INDEX:
                print(f"ไม่รู้จักปุ่ม {key!r}")
                return 2
            colors[key] = (byte_value(r), byte_value(g), byte_value(b))
    with Link("control", dry_run=args.dry_run) as link:
        try:
            KeyboardLight(link).set_per_key(colors, hold=args.hold or args.random, randomize=args.random)
        except KeyboardInterrupt:
            pass
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amg65", description="ควบคุมไฟ/จอ LEOBOG AMG65")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="ดู scene ทั้งหมด")
    p_list.set_defaults(func=cmd_list)

    p_doctor = sub.add_parser("doctor", help="ตรวจสภาพ HID endpoint")
    p_doctor.set_defaults(func=cmd_doctor)

    p_show = sub.add_parser("show", help="เล่น scene บนจอ LED")
    p_show.add_argument("scene", choices=tuple(scenes.REGISTRY))
    p_show.add_argument("--preview", action="store_true", help="แสดงในเทอร์มินัลด้วย")
    p_show.add_argument("--no-device", action="store_true", help="ไม่ต้องต่อคีย์บอร์ด (preview อย่างเดียว)")
    p_show.add_argument("--fps", type=float, default=None, help="บังคับ FPS (ปกติ scene กำหนดเอง)")
    p_show.add_argument("--seconds", type=float, default=None, help="เล่นกี่วินาทีแล้วออก")
    p_show.add_argument("--text", help="ข้อความสำหรับ scene marquee")
    p_show.add_argument("--delay", type=float, default=8.5, help="หน่วงระหว่าง HID packet (ms)")
    p_show.add_argument("--lean", action="store_true", help="ตัด header/flush ต่อเฟรม (เร็วขึ้น ดู bench_fps.py)")
    p_show.set_defaults(func=cmd_show)

    p_light = sub.add_parser("light", help="เอฟเฟกต์ไฟใต้ปุ่มของเฟิร์มแวร์")
    p_light.add_argument("effect", choices=tuple(MODES))
    p_light.add_argument("--rgb", nargs=3, type=byte_value, default=(255, 255, 255), metavar=("R", "G", "B"))
    p_light.add_argument("--brightness", type=level_value, default=5)
    p_light.add_argument("--speed", type=level_value, default=3)
    p_light.add_argument("--direction", type=int, choices=(0, 1, 2, 3), default=0)
    p_light.add_argument("--colorful", action="store_true")
    p_light.add_argument("--dry-run", action="store_true")
    p_light.set_defaults(func=cmd_light)

    p_keys = sub.add_parser("keys", help="กำหนดสีรายปุ่ม")
    p_keys.add_argument("--key", action="append", nargs=4, metavar=("KEY", "R", "G", "B"))
    p_keys.add_argument("--random", action="store_true", help="สุ่มสีต่อเนื่อง")
    # Custom Light ส่งค่า RGB ตรง ๆ ไม่มีช่อง brightness — รับไว้เฉย ๆ ให้คำสั่งเดิมไม่พัง
    p_keys.add_argument("--brightness", type=level_value, help=argparse.SUPPRESS)
    p_keys.add_argument("--hold", action="store_true", help="ส่งซ้ำจนกด Ctrl+C (Custom Light ต้องใช้)")
    p_keys.add_argument("--dry-run", action="store_true")
    p_keys.set_defaults(func=cmd_keys)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
