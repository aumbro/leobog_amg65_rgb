"""หน้าบ้านบรรทัดคำสั่งของ amg65"""
from __future__ import annotations

import argparse
import sys
import time

from . import scenes
from .device import (
    CONTROL_REPORT_BYTES,
    AlreadyRunning,
    DeviceNotFound,
    EndpointStalled,
    Link,
    claim_exclusive,
    find_path,
)
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

    # การทดสอบเขียนของ doctor ก็คือการเขียนเข้า endpoint จริง ถ้ามีโปรแกรมอื่น
    # กำลังสตรีมอยู่ ก็จะกลายเป็นสองโปรเซสเขียนพร้อมกัน = สาเหตุที่ทำให้ค้าง
    # จึงตรวจได้แค่ระดับ enumerate เท่านั้นในกรณีนั้น
    try:
        claim_exclusive()
    except AlreadyRunning:
        print(
            "\nมีโปรแกรม amg65 อีกตัวถืออุปกรณ์อยู่ — ข้ามการทดสอบเขียน"
            "\n  (เขียนซ้อนกันคือสาเหตุที่ทำให้ endpoint ค้าง)"
            "\n  ปิดตัวนั้นก่อนถ้าอยากตรวจเต็มรูปแบบ"
        )
        return 0

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
                data_delay=None if args.delay_data is None else args.delay_data / 1000.0,
                command_delay=None if args.delay_cmd is None else args.delay_cmd / 1000.0,
            )
            sinks.append(MatrixSink(matrix))
        except (OSError, DeviceNotFound) as exc:
            print(f"เปิดคีย์บอร์ดไม่ได้: {exc}\nรันต่อด้วย --preview อย่างเดียว\n")
            args.preview = True
    if args.preview or not sinks:
        sinks.append(PreviewSink())

    sink = sinks[0] if len(sinks) == 1 else MultiSink(*sinks)
    engine = Engine(sink, fps=args.fps)
    stalled = False
    try:
        engine.run(scene, duration=args.seconds)
    except KeyboardInterrupt:
        pass
    except EndpointStalled as exc:
        stalled = True
        print(f"\nหยุดเพราะ endpoint ค้าง:\n{exc}")
    finally:
        sink.close()
        if link is not None:
            link.close()
    dropped = getattr(sink, "drops", 0)
    print(f"\nจบ — FPS จริงล่าสุด {engine.actual_fps:.1f}" + (f", เฟรมหลุด {dropped}" if dropped else ""))
    return 1 if stalled else 0


def cmd_tray(args: argparse.Namespace) -> int:
    try:
        from .tray import Tray
    except ImportError as exc:
        print(f"tray ต้องใช้ pystray กับ pillow — pip install pystray pillow\n  ({exc})")
        return 2
    return Tray(args.scene, args.delay).run()


def cmd_upload(args: argparse.Namespace) -> int:
    """เบคเฟรมแล้วเก็บลงเครื่อง — เล่นวนเองโดยไม่ต้องมีโปรแกรมค้าง"""
    from . import bake
    from .matrix import fps_for_speed, speed_for_fps

    if bool(args.source) == bool(args.scene):
        print("ต้องระบุอย่างใดอย่างหนึ่ง: ไฟล์ภาพ/GIF หรือ --scene")
        return 2

    # --play-fps คือหน้าบ้านของไบต์ speed; ผูกกับ FPS ที่ใช้เรนเดอร์ด้วย
    # ไม่งั้นภาพจะเคลื่อนที่เร็ว/ช้าไม่ตรงกับที่ scene ออกแบบไว้
    speed = args.speed if args.play_fps is None else speed_for_fps(args.play_fps)
    # ⚠️ ต้องเรนเดอร์ด้วย FPS *จริง* ที่เครื่องจะเล่น ไม่ใช่ค่าที่ขอมา
    # ไบต์ speed เป็นจำนวนเต็มหน่วยละ 10 ms ค่าที่ขอจึงมักถูกปัด (ขอ 33 ได้จริง 31.2)
    # ถ้าเรนเดอร์ด้วยค่าที่ขอ ภาพจะเลื่อนไม่ครบรอบแล้วกระโดดทุกครั้งที่วนลูป
    render_fps = args.render_fps or fps_for_speed(speed)

    try:
        if args.scene:
            kwargs = {}
            frame_count = args.frames or bake.frames_for_loop(args.scene, render_fps) or 60
            if args.frames is None and frame_count != 60:
                print(f"ใช้ {frame_count} เฟรม = ความยาวลูปของ scene พอดีที่ {render_fps:.1f} FPS")
            if args.scene in ("marquee", "nowplaying"):
                if args.text:
                    kwargs["text"] = args.text
                chosen = args.scroll_speed
                if chosen is None and args.text:
                    # เลือกความเร็วที่ทำให้ข้อความเลื่อนครบหนึ่งรอบพอดีในจำนวนเฟรมที่มี
                    # ไม่งั้นเฟรมสุดท้ายกับเฟรมแรกไม่ต่อกัน แล้วภาพกระโดดทุกครั้งที่วนลูป
                    chosen = bake.seamless_scroll_speed(args.text, frame_count, render_fps)
                    if chosen:
                        print(f"เลือกความเร็วเลื่อนอัตโนมัติ {chosen:.1f} px/วินาที (ลูปต่อเนียนพอดี)")
                if chosen:
                    kwargs["speed"] = chosen
            frames = bake.frames_from_scene(
                args.scene, frame_count, render_fps, args.brightness, **kwargs
            )
        else:
            # ไฟล์ภาพมีจำนวนเฟรมของมันเองอยู่แล้ว ไม่ระบุ = เอาทั้งหมดเท่าที่โควตาไหว
            # (ถ้า default เป็น 60 GIF 83 เฟรมจะโดนสุ่มทิ้งไปเงียบ ๆ)
            frames = bake.frames_from_image(
                args.source, args.fit, args.brightness, args.frames or bake.MAX_FRAMES
            )
    except (KeyError, ImportError, ValueError, OSError) as exc:
        print(f"เบคเฟรมไม่สำเร็จ: {exc}")
        return 2

    size = bake.payload_size(len(frames))
    chunks = (size + 4095) // 4096
    actual_fps = fps_for_speed(speed)
    print(
        f"ได้ {len(frames)} เฟรม, payload {size:,} ไบต์ = {chunks} ก้อน"
        f" (อัปโหลดราว {chunks * 0.17:.1f} วินาที)"
    )
    print(
        f"เล่นที่ speed 0x{speed:02X} = {actual_fps:.1f} FPS"
        f" → ลูปยาว {len(frames) / actual_fps:.1f} วินาที"
    )
    if args.play_fps and abs(actual_fps - args.play_fps) / args.play_fps > 0.15:
        # ไบต์ speed เป็นจำนวนเต็มหน่วยละ 10 ms ค่า FPS สูง ๆ จึงปัดแล้วเพี้ยนได้เยอะ
        print(f"  (ขอ {args.play_fps:.0f} FPS แต่ปัดลงหน่วย 10 ms ได้ {actual_fps:.1f})")
    if chunks > bake.SAFE_CHUNKS:
        print(
            f"⚠️  {chunks} ก้อน เกินขนาดที่เชื่อถือได้ ({bake.SAFE_CHUNKS} ก้อน)\n"
            f"   ยิ่งใหญ่ยิ่งเสี่ยง endpoint ค้างหรือภาพเพี้ยน (47 ก้อนพังไป 1 ใน 2 ครั้ง)\n"
            f"   ลด --frames ลงแล้วลด --play-fps ตามส่วน จะได้ลูปยาวเท่าเดิมด้วยข้อมูลน้อยลง"
        )

    if args.preview:
        from . import preview

        preview.enable_ansi()
        preview.clear_screen()
        try:
            for loop in range(args.preview_loops):
                for index, canvas in enumerate(frames):
                    preview.draw(canvas, f"เฟรม {index + 1}/{len(frames)} (รอบ {loop + 1})")
                    time.sleep(1.0 / max(args.render_fps or 15.0, 1.0))
        except KeyboardInterrupt:
            pass
        if args.no_upload:
            return 0

    if args.no_upload:
        print("--no-upload: ไม่ส่งเข้าเครื่อง")
        return 0

    try:
        with Link("control") as control, Link("bulk") as bulk:
            matrix = Matrix(control)
            print("กำลังอัปโหลด ...")
            matrix.upload_animation(
                bulk, frames, speed=speed,
                on_progress=lambda done, total: print(f"  {done}/{total}", end="\r", flush=True),
                chunk_delay=args.chunk_delay / 1000.0,
            )
        print("\nอัปโหลดเสร็จ — เฟิร์มแวร์เล่นวนเองแล้ว ปิดโปรแกรมได้เลย")
    except EndpointStalled as exc:
        print(f"\n{exc}")
        return 1
    except (OSError, DeviceNotFound) as exc:
        print(f"\nอัปโหลดไม่สำเร็จ: {exc}")
        return 1
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
    p_show.add_argument(
        "--delay-data", type=float, default=None,
        help="หน่วงเฉพาะระหว่าง RGB 15 reports (ms) — ไม่ระบุ = ใช้ค่า --delay",
    )
    p_show.add_argument(
        "--delay-cmd", type=float, default=None,
        help="หน่วงเฉพาะหลังคำสั่ง 04 18 / 04 35 / flush / 04 02 (ms)",
    )
    p_show.add_argument("--lean", action="store_true", help="ตัด header/flush ต่อเฟรม (เร็วขึ้น ดู bench_fps.py)")
    p_show.set_defaults(func=cmd_show)

    p_tray = sub.add_parser("tray", help="ไอคอนถาดระบบ สลับ scene ได้ ไม่ต้องเปิดคอนโซลค้าง")
    p_tray.add_argument("--scene", choices=tuple(scenes.REGISTRY), default="clock")
    p_tray.add_argument("--delay", type=float, default=8.5, help="หน่วงระหว่าง HID packet (ms)")
    p_tray.set_defaults(func=cmd_tray)

    p_upload = sub.add_parser(
        "upload", help="เบคเฟรมเก็บลงเครื่อง แล้วเฟิร์มแวร์เล่นวนเอง (ลื่นกว่า stream)"
    )
    p_upload.add_argument("source", nargs="?", help="ไฟล์ภาพหรือ GIF")
    p_upload.add_argument("--scene", choices=tuple(scenes.REGISTRY), help="เบคจาก scene แทนไฟล์")
    p_upload.add_argument(
        "--frames", type=int, default=None,
        help="จำนวนเฟรม สูงสุด 255 (ไม่ระบุ: scene = 60, ไฟล์ = เท่าที่ไฟล์มี)",
    )
    p_upload.add_argument("--render-fps", type=float, default=None, help="FPS ที่ใช้ตอนเรนเดอร์ scene")
    p_upload.add_argument("--brightness", type=float, default=1.0, help="ตัวคูณความสว่าง 0-1")
    p_upload.add_argument(
        "--fit", choices=("cover", "fit", "stretch"), default="cover",
        help="วิธีย่อภาพลงจอ 63x5 (จออัตราส่วน 12.6:1)",
    )
    p_upload.add_argument("--text", help="ข้อความ ถ้าเบคจาก scene marquee")
    p_upload.add_argument(
        "--scroll-speed", type=float, default=None,
        help="ความเร็วเลื่อนข้อความ พิกเซล/วินาที — ยิ่งเล่นเร็วยิ่งต้องเลื่อนเร็วตาม "
             "ไม่งั้นลูปยาวเกิน 255 เฟรมแล้วภาพกระโดด",
    )
    p_upload.add_argument(
        "--play-fps", type=float, default=None,
        help="ความเร็วเล่นบนเครื่อง 2-83 FPS (ใช้เป็น FPS ตอนเรนเดอร์ scene ด้วย)",
    )
    p_upload.add_argument(
        "--speed", type=lambda s: int(s, 0), default=0x0C,
        help="ค่าหน่วงต่อเฟรมดิบ หน่วยละ 10 ms (ทางการใช้ 0x0C = 8.3 FPS); --play-fps ทับค่านี้",
    )
    p_upload.add_argument(
        "--chunk-delay", type=float, default=170.0,
        help="หน่วงระหว่างก้อนข้อมูล 4KB (ms) — เพิ่มถ้า MI_03 ค้างบ่อย",
    )
    p_upload.add_argument("--preview", action="store_true", help="ดูเฟรมในเทอร์มินัลก่อน")
    p_upload.add_argument("--preview-loops", type=int, default=2, help="วนดูกี่รอบ")
    p_upload.add_argument("--no-upload", action="store_true", help="ไม่ต้องส่งเข้าเครื่อง")
    p_upload.set_defaults(func=cmd_upload)

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


# คำสั่งที่เขียนเข้าอุปกรณ์จริง ต้องมีตัวเดียวในระบบ
_EXCLUSIVE = {"show", "tray", "upload", "keys", "light"}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # ธงที่แปลว่า "ไม่แตะอุปกรณ์" — คำสั่งพวกนี้รันพร้อมกับตัวที่ถือล็อกอยู่ได้
    offline = any(
        getattr(args, flag, False) for flag in ("dry_run", "no_device", "no_upload")
    )
    if args.command in _EXCLUSIVE and not offline:
        try:
            claim_exclusive()
        except AlreadyRunning as exc:
            print(exc)
            return 2
    return args.func(args)
