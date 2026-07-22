"""เกมบนจอ 63×5 — ไดโนกระโดด (เล่นได้) และปิงปองที่เล่นเอง

จอสูง 5 พิกเซล เตี้ยมากจนเกมส่วนใหญ่เล่นไม่ได้ ไดโนวิ่งเลยเหมาะที่สุด เพราะ
กติกาทั้งเกมอยู่บนแกนเดียว: อยู่บนพื้น หรือลอย

    แถว 0–3  พื้นที่เล่น (ไดโนสูง 3, กระโดดสูงสุด 3 พิกเซล)
    แถว 4    พื้น
    x 56–62  แผงขวา = คะแนน 2 หลัก (3+1+3 = 7 พอดี)

กดปุ่มได้เฉพาะตอนหน้าต่างคอนโซลโฟกัสอยู่ (engine ใช้ msvcrt ไม่ใช่ global hook)
    space / ลูกศรขึ้น = กระโดด    r = เริ่มใหม่
"""
from __future__ import annotations

import random

from ..matrix import HEIGHT, MAIN_WIDTH, WIDTH, Canvas
from .base import Scene

GROUND_Y = 4
PLAY_WIDTH = MAIN_WIDTH  # กันไม่ให้กระบองเพชรวิ่งไปทับช่องคะแนน

DINO_COLOR = (90, 254, 120)
CACTUS_COLOR = (0, 200, 60)
GROUND_COLOR = (24, 24, 30)
DEAD_COLOR = (254, 40, 40)


class DinoScene(Scene):
    name = "dino"
    description = "เกมไดโนกระโดดข้ามกระบองเพชร (กด space)"
    fps = 24.0

    def __init__(self, dino_x: int = 4) -> None:
        self.dino_x = dino_x
        self.reset()

    def reset(self) -> None:
        self.height = 0.0        # ความสูงเหนือพื้น (พิกเซล)
        self.velocity = 0.0
        self.obstacles: list[tuple[float, int]] = []  # (x, ความสูง 1–2)
        self.speed = 17.0        # พิกเซล/วินาที ค่อย ๆ เร็วขึ้น
        self.score = 0
        self.dead_for = 0.0
        self.distance = 0.0
        self._spawn_gap = 26.0

    # ---------- input ----------

    def on_key(self, key: str) -> None:
        if key in ("space", "up", "w"):
            # กระโดดได้เฉพาะตอนเท้าติดพื้น — กันกดรัวลอยค้าง
            if self.dead_for <= 0.0 and self.height <= 0.01:
                self.velocity = 15.0
        elif key == "r":
            self.reset()

    # ---------- ฟิสิกส์ ----------

    def _step(self, dt: float) -> None:
        if self.dead_for > 0.0:
            self.dead_for -= dt
            if self.dead_for <= 0.0:
                self.reset()
            return

        self.velocity -= 52.0 * dt          # แรงโน้มถ่วง
        self.height = max(0.0, self.height + self.velocity * dt)
        if self.height <= 0.0:
            self.velocity = 0.0

        move = self.speed * dt
        self.distance += move
        self.speed = min(38.0, 17.0 + self.distance / 90.0)  # ยิ่งไกลยิ่งเร็ว

        self.obstacles = [(x - move, h) for x, h in self.obstacles if x - move > -2]
        rightmost = max((x for x, _ in self.obstacles), default=-999.0)
        if rightmost < PLAY_WIDTH - self._spawn_gap:
            self.obstacles.append((float(PLAY_WIDTH + 1), random.choice((1, 1, 2))))
            # ระยะห่างสุ่มใหม่ทุกครั้ง ไม่งั้นจังหวะกระโดดจะซ้ำจนน่าเบื่อ
            self._spawn_gap = random.uniform(20.0, 34.0)

        self.score = int(self.distance / 10.0)
        if self._collides():
            self.dead_for = 1.2

    def _collides(self) -> bool:
        foot = self.height           # เท้าอยู่สูงจากพื้นเท่านี้
        for x, obstacle_height in self.obstacles:
            # ไดโนกว้าง 2 px เริ่มที่ dino_x
            if x < self.dino_x + 2 and x > self.dino_x - 1:
                if foot < obstacle_height:
                    return True
        return False

    # ---------- วาด ----------

    def render(self, canvas: Canvas, elapsed: float, frame: int) -> None:
        self._step(1.0 / self.fps)

        for x in range(PLAY_WIDTH):
            canvas.set(x, GROUND_Y, GROUND_COLOR)

        color = DEAD_COLOR if self.dead_for > 0.0 else CACTUS_COLOR
        for x, obstacle_height in self.obstacles:
            column = int(round(x))
            for step in range(obstacle_height):
                canvas.set(column, GROUND_Y - 1 - step, color)

        self._draw_dino(canvas, frame)
        self._draw_score(canvas)

    def _draw_dino(self, canvas: Canvas, frame: int) -> None:
        color = DEAD_COLOR if self.dead_for > 0.0 else DINO_COLOR
        lift = int(round(self.height))
        base = GROUND_Y - 1 - lift  # แถวของเท้า
        canvas.set(self.dino_x, base - 2, color)
        canvas.set(self.dino_x + 1, base - 2, color)
        canvas.set(self.dino_x, base - 1, color)
        canvas.set(self.dino_x + 1, base - 1, color)
        if self.height > 0.01 or self.dead_for > 0.0:
            canvas.set(self.dino_x, base, color)
            canvas.set(self.dino_x + 1, base, color)
        else:
            # สลับขาให้ดูเหมือนวิ่ง
            canvas.set(self.dino_x + (frame // 3) % 2, base, color)

    def _draw_score(self, canvas: Canvas) -> None:
        color = DEAD_COLOR if self.dead_for > 0.0 else (254, 200, 40)
        canvas.text(f"{self.score % 100:02d}", MAIN_WIDTH, color)


class PongScene(Scene):
    name = "pong"
    description = "ปิงปองเล่นเอง ดูเพลิน ๆ"
    fps = 24.0

    PADDLE_HEIGHT = 2

    def __init__(self) -> None:
        self.reset(direction=1)
        self.score = [0, 0]

    def reset(self, direction: int) -> None:
        self.ball_x = WIDTH / 2.0
        self.ball_y = HEIGHT / 2.0
        self.vx = 26.0 * direction
        self.vy = random.uniform(-7.0, 7.0)
        self.left = 1.5
        self.right = 1.5
        self.trail: list[tuple[float, float]] = []

    def _track(self, position: float, target: float, dt: float, speed: float) -> float:
        """ไล่ลูกแบบมีขีดจำกัดความเร็ว — ทำให้พลาดได้บ้าง ไม่งั้นตีกันไม่จบ."""
        limit = speed * dt
        delta = max(-limit, min(limit, target - position))
        return max(0.0, min(HEIGHT - self.PADDLE_HEIGHT, position + delta))

    def render(self, canvas: Canvas, elapsed: float, frame: int) -> None:
        dt = 1.0 / self.fps
        self.ball_x += self.vx * dt
        self.ball_y += self.vy * dt

        if self.ball_y < 0.0:
            self.ball_y, self.vy = 0.0, abs(self.vy)
        elif self.ball_y > HEIGHT - 1:
            self.ball_y, self.vy = HEIGHT - 1.0, -abs(self.vy)

        # ไม้ฝั่งที่ลูกวิ่งเข้าหาไล่จริง อีกฝั่งเลื้อยกลับกลาง
        aim = self.ball_y - (self.PADDLE_HEIGHT - 1) / 2.0
        if self.vx < 0:
            self.left = self._track(self.left, aim, dt, 15.0)
            self.right = self._track(self.right, (HEIGHT - self.PADDLE_HEIGHT) / 2.0, dt, 5.0)
        else:
            self.right = self._track(self.right, aim, dt, 15.0)
            self.left = self._track(self.left, (HEIGHT - self.PADDLE_HEIGHT) / 2.0, dt, 5.0)

        if self.ball_x <= 1.0 and self.vx < 0:
            if self.left - 0.6 <= self.ball_y <= self.left + self.PADDLE_HEIGHT - 0.4:
                self.ball_x, self.vx = 1.0, abs(self.vx)
                self.vy += (self.ball_y - (self.left + 0.5)) * 9.0
            elif self.ball_x < -1.0:
                self.score[1] += 1
                self.reset(direction=1)
        elif self.ball_x >= WIDTH - 2.0 and self.vx > 0:
            if self.right - 0.6 <= self.ball_y <= self.right + self.PADDLE_HEIGHT - 0.4:
                self.ball_x, self.vx = WIDTH - 2.0, -abs(self.vx)
                self.vy += (self.ball_y - (self.right + 0.5)) * 9.0
            elif self.ball_x > WIDTH + 1.0:
                self.score[0] += 1
                self.reset(direction=-1)

        self.vy = max(-16.0, min(16.0, self.vy))

        self.trail.append((self.ball_x, self.ball_y))
        del self.trail[:-5]
        for index, (tx, ty) in enumerate(self.trail[:-1]):
            canvas.blend(int(round(tx)), int(round(ty)), (0, 120, 254), 0.10 + 0.10 * index)

        for step in range(self.PADDLE_HEIGHT):
            canvas.set(0, int(round(self.left)) + step, (254, 60, 60))
            canvas.set(WIDTH - 1, int(round(self.right)) + step, (60, 160, 254))
        canvas.set(int(round(self.ball_x)), int(round(self.ball_y)), (254, 254, 254))
