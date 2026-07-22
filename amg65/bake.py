"""เบคภาพ/GIF/scene ให้เป็นชุดเฟรม 63×5 สำหรับอัปโหลดเก็บลงเครื่อง

ทำไมต้องเบค: live stream ตันที่ ~5-6 FPS (ส่งเร็วกว่านั้นเครื่องทิ้ง report เงียบ ๆ
จนพิกเซลไปโผล่ผิดที่ ดู §9.3 ของ AMG65_REVERSE_ENGINEERING.md) แต่ถ้าอัปโหลดเก็บ
ลงเครื่องผ่าน MI_03 เฟิร์มแวร์เล่นวนเอง ไม่มีทราฟฟิก USB ระหว่างเล่น จึงลื่นและค้างไม่ได้

แลกมาด้วยการที่ภาพต้องรู้ล่วงหน้า — ใช้กับ scene ที่ต้องการข้อมูลสด (clock, vis,
sysmon, nowplaying) ไม่ได้ ต้องเป็นลูปที่วนซ้ำได้เท่านั้น
"""
from __future__ import annotations

from .matrix import HEIGHT, WIDTH, Canvas

MAX_FRAMES = 255  # จำนวนเฟรมสูงสุดที่ header รองรับ (byte เดียว)

# เพดานที่ "ส่งได้" กับที่ "ส่งแล้วเชื่อถือได้" ไม่เท่ากัน
# ผลจริง: 35 ก้อนผ่าน, 47 ก้อนผ่าน, 58 ก้อนพัง 3 ครั้งติด (ค้าง 1 + ภาพเพี้ยน 2)
# 59 ก้อนเคยผ่านครั้งเดียวจึงยังเชื่อไม่ได้ ตั้งเส้นเตือนไว้ที่ 47 ก้อน
SAFE_CHUNKS = 47


def _to_canvas(image, brightness: float) -> Canvas:
    """PIL RGB image ขนาด 63×5 → Canvas."""
    canvas = Canvas()
    pixels = list(image.getdata())
    scale = max(0.0, min(1.0, brightness))
    canvas.pixels = [
        (int(r * scale), int(g * scale), int(b * scale)) for r, g, b in pixels
    ]
    return canvas


def _resize(image, mode: str):
    """ย่อ/ขยายภาพให้ลง 63×5

    จอนี้อัตราส่วน 12.6:1 ซึ่งสุดโต่งมาก ภาพทั่วไปย่อแบบ 'fit' จะเหลือสูงไม่กี่พิกเซล
    จนดูไม่ออก ค่าเริ่มต้นจึงเป็น 'cover' (เต็มจอแล้วตัดส่วนเกิน)
    """
    from PIL import Image

    if image.size == (WIDTH, HEIGHT):
        return image
    if mode == "stretch":
        return image.resize((WIDTH, HEIGHT), Image.LANCZOS)

    source_ratio = image.width / image.height
    target_ratio = WIDTH / HEIGHT
    if mode == "cover":
        if source_ratio > target_ratio:
            height = HEIGHT
            width = max(WIDTH, round(HEIGHT * source_ratio))
        else:
            width = WIDTH
            height = max(HEIGHT, round(WIDTH / source_ratio))
        resized = image.resize((width, height), Image.LANCZOS)
        left = (width - WIDTH) // 2
        top = (height - HEIGHT) // 2
        return resized.crop((left, top, left + WIDTH, top + HEIGHT))

    # fit: ย่อให้อยู่ในกรอบทั้งหมดแล้วเติมดำ
    if source_ratio > target_ratio:
        width, height = WIDTH, max(1, round(WIDTH / source_ratio))
    else:
        width, height = max(1, round(HEIGHT * source_ratio)), HEIGHT
    resized = image.resize((width, height), Image.LANCZOS)
    canvas_image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    canvas_image.paste(resized, ((WIDTH - width) // 2, (HEIGHT - height) // 2))
    return canvas_image


def frames_from_image(
    path: str,
    mode: str = "cover",
    brightness: float = 1.0,
    max_frames: int = MAX_FRAMES,
) -> list[Canvas]:
    """อ่านไฟล์ภาพหรือ GIF → ชุดเฟรม (ภาพนิ่งได้เฟรมเดียว)."""
    from PIL import Image, ImageSequence

    rendered: list = []
    with Image.open(path) as image:
        # ⚠️ ห้ามเก็บ list(ImageSequence.Iterator(...)) ไว้แปลงทีหลัง — ทุกตัวใน list
        # เป็น reference ของ object เดียวกันที่ถูก seek ไปมา จะได้เฟรมสุดท้ายซ้ำทั้งชุด
        # ต้องแปลงเป็นภาพใหม่ระหว่างวนเท่านั้น
        stage = Image.new("RGBA", image.size, (0, 0, 0, 255))
        for frame in ImageSequence.Iterator(image):
            # GIF ส่วนใหญ่เก็บเฉพาะส่วนที่เปลี่ยน ต้องซ้อนทับสะสมถึงจะได้ภาพเต็ม
            stage.alpha_composite(frame.convert("RGBA"))
            rendered.append(stage.convert("RGB"))

    if not rendered:
        raise ValueError(f"อ่านเฟรมจาก {path} ไม่ได้เลย")
    # ยาวเกินโควตาให้สุ่มเก็บกระจายทั้งคลิป ไม่ใช่ตัดท้ายทิ้ง
    if len(rendered) > max_frames:
        step = len(rendered) / max_frames
        rendered = [rendered[int(i * step)] for i in range(max_frames)]
    return [_to_canvas(_resize(frame, mode), brightness) for frame in rendered]


def frames_from_scene(
    name: str,
    count: int,
    fps: float | None = None,
    brightness: float = 1.0,
    **scene_kwargs,
) -> list[Canvas]:
    """เรนเดอร์ scene ที่มีอยู่แล้วเป็นชุดเฟรม แทนที่จะสตรีมสด

    ใช้ scene engine เดิมทั้งดุ้น — scene ไม่ต้องรู้เลยว่าถูกเบคหรือถูกสตรีม
    """
    from . import scenes

    if not 1 <= count <= MAX_FRAMES:
        raise ValueError(f"จำนวนเฟรมต้องอยู่ระหว่าง 1-{MAX_FRAMES}")
    scene = scenes.load(name)(**scene_kwargs)
    rate = fps or scene.fps
    scene.start()
    try:
        baked = []
        for index in range(count):
            canvas = Canvas()
            scene.render(canvas, index / rate, index)
            if brightness < 1.0:
                canvas.scale_brightness(brightness)
            baked.append(canvas)
        return baked
    finally:
        scene.stop()


def seamless_scroll_speed(text: str, frame_count: int, play_fps: float) -> float | None:
    """ความเร็วเลื่อน (px/วินาที) ที่ทำให้ข้อความวนครบรอบพอดีในจำนวนเฟรมที่มี

    ทั้งสามค่านี้ผูกกันเป็นสมการเดียว เลือกได้แค่สองค่า ค่าที่สามถูกบังคับ:

        จำนวนเฟรม = ระยะทางที่ต้องเลื่อน ÷ ความเร็วเลื่อน × FPS ที่เล่น

    ถ้าไม่พอดี เฟรมสุดท้ายกับเฟรมแรกจะไม่ต่อกัน แล้วภาพกระโดดทุกครั้งที่วนลูป
    คืน None ถ้าข้อความสั้นกว่าจอ (กรณีนั้นจัดกลางอยู่นิ่ง ไม่ได้เลื่อน)
    """
    from . import font
    from .scenes.nowplaying import GAP

    width = font.text_width(text)
    if width <= WIDTH:
        return None
    loop_seconds = frame_count / play_fps
    return (width + GAP) / loop_seconds


def payload_size(frame_count: int) -> int:
    """ขนาด payload ที่จะส่ง (ไว้เตือนก่อนอัปโหลดว่าจะใช้เวลานานแค่ไหน)."""
    body = 4 + frame_count * WIDTH * HEIGHT * 3
    return body + (3 if frame_count == 1 else 2)
