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

# เพดานที่ "ส่งได้" กับที่ "ส่งแล้วเชื่อถือได้" ไม่เท่ากัน และไม่มีเส้นตายชัด ๆ
# ยิ่งใหญ่ยิ่งเสี่ยงแบบค่อย ๆ ไต่:
#     35 ก้อน  ผ่าน 2/2
#     44 ก้อน  ผ่าน 1/1
#     47 ก้อน  ผ่าน 1/2   <- เคยตั้งเป็นเส้นปลอดภัย แล้วพังจริง
#     58 ก้อน  ผ่าน 0/3   (ค้าง 1 + ภาพเพี้ยน 2)
#     59 ก้อน  ผ่าน 1/1
# เพิ่ม chunk_delay ไม่ช่วย — รอบที่พังที่ 47 ก้อนใช้ 220ms ส่วนรอบที่ผ่านใช้ 170ms
# ตัวแปรจริงคือขนาดรวม ไม่ใช่ความถี่ที่ส่ง
SAFE_CHUNKS = 40


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
            if scene.loop_seconds:
                # scene ที่วนได้: แบ่งลูปเป็น count ส่วนเท่า ๆ กัน เฟรมสุดท้ายจึงต่อ
                # เฟรมแรกพอดีเสมอ ไม่ว่าจำนวนเฟรมจะปัดเป็นเลขอะไร
                # (ถ้าเดินทีละ 1/FPS แล้วจำนวนเฟรมปัด ลูปจะเลยหรือขาดนิดหน่อยทุกครั้ง)
                elapsed = scene.loop_seconds * index / count
            else:
                elapsed = index / rate
            scene.render(canvas, elapsed, index)
            if brightness < 1.0:
                canvas.scale_brightness(brightness)
            baked.append(canvas)
        return baked
    finally:
        scene.stop()


def frames_for_loop(scene_name: str, play_fps: float) -> int | None:
    """จำนวนเฟรมที่ทำให้ scene วนกลับมาพอดีที่ FPS นั้น

    คืน None ถ้า scene ไม่ได้บอกความยาวลูปไว้ (คือมันไม่ได้วน)
    ถ้าคำนวณแล้วเกินโควตา 255 เฟรม จะย่นให้เหลือ 255 ซึ่งลูปจะไม่พอดีอีกต่อไป
    — กรณีนั้นควรลด FPS ลงแทน
    """
    from . import scenes

    try:
        loop_seconds = scenes.load(scene_name).loop_seconds
    except (KeyError, ImportError):
        return None
    if not loop_seconds:
        return None
    return max(1, min(MAX_FRAMES, round(loop_seconds * play_fps)))


def loopable_scenes() -> list[str]:
    """scene ที่เบคเก็บลงเครื่องแล้ววนได้เนียน (มี loop_seconds)."""
    from . import scenes

    names = []
    for name in scenes.REGISTRY:
        try:
            if scenes.load(name).loop_seconds:
                names.append(name)
        except (KeyError, ImportError):
            continue
    return names


def plan_upload(scene_name: str, max_chunks: int = None) -> tuple[int, float] | None:
    """เลือกจำนวนเฟรมกับ FPS ที่ดีที่สุดสำหรับ scene นี้ ภายในขนาดที่ปลอดภัย

    คืน (จำนวนเฟรม, FPS ที่จะเล่น) หรือ None ถ้า scene นั้นวนไม่ได้

    ตรรกะ: อยากได้ FPS สูงที่สุดเท่าที่ยังไม่เกินขนาดปลอดภัย เพราะภาพยิ่งลื่นยิ่งดี
    แต่ลูปยาวเท่าเดิมเสมอ (= loop_seconds ของ scene) จึงลด FPS ลงถ้าเฟรมเกินโควตา
    """
    from . import scenes

    if max_chunks is None:
        max_chunks = SAFE_CHUNKS
    try:
        loop_seconds = scenes.load(scene_name).loop_seconds
    except (KeyError, ImportError):
        return None
    if not loop_seconds:
        return None

    # เฟรมสูงสุดที่ยังอยู่ในขนาดปลอดภัย
    budget = min(MAX_FRAMES, int((max_chunks * 4096 - 6) / (WIDTH * HEIGHT * 3)))
    for fps in (30.0, 25.0, 20.0, 15.0, 12.0, 10.0, 8.0, 6.0, 4.0):
        frames = round(loop_seconds * fps)
        if 1 <= frames <= budget:
            return frames, fps
    return max(1, budget), budget / loop_seconds


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
