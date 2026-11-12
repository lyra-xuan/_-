"""游戏主循环与场景逻辑。

采用「夹紧的时间步长」推进逻辑：每帧用 ``clock.tick`` 得到真实 elapsed，
并夹紧到 ``MAX_DT``，保证物理与碰撞在不同机器上表现一致，同时避免卡顿后穿模。
"""
from __future__ import annotations

import math
import random

import pygame
from pygame.math import Vector2

from . import config, collision
from .entities import Bullet, Player, draw_translucent_circle


def _load_font(size: int) -> pygame.font.Font:
    """按优先级挑选一个能显示中文的系统字体。"""
    for name in ("microsoftyahei", "microsoftyaheiui", "simhei", "simsun"):
        path = pygame.font.match_font(name)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


class Game:
    """游戏主体：窗口、主循环、输入、碰撞与渲染。"""

    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((config.SCREEN_W, config.SCREEN_H))
        pygame.display.set_caption("弹幕射击 - 碰撞检测 Demo")
        self.clock = pygame.time.Clock()
        self.font = _load_font(18)
        self.font_big = _load_font(30)

        self.running = True
        self.paused = False

        self.player = Player(config.SCREEN_W / 2, config.SCREEN_H - 80)
        self.bullets: list[Bullet] = []
        self.graze_total = 0
        self.hit_total = 0
        self.hit_flash = 0.0          # 命中时的红屏闪烁计时
        self.spawn_timer = 0.0

    # ------------------------------------------------------------------ #
    # 输入
    # ------------------------------------------------------------------ #
    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key in (pygame.K_p, pygame.K_SPACE):
                    self.paused = not self.paused

    def _read_player_input(self) -> bool:
        """读取方向键设置玩家速度，返回是否处于低速（focus）状态。"""
        keys = pygame.key.get_pressed()
        move = Vector2(0.0, 0.0)
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            move.x -= 1.0
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            move.x += 1.0
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            move.y -= 1.0
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            move.y += 1.0

        focus = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        if move.length_squared() > 0:
            move = move.normalize()
        speed = config.PLAYER_SPEED * (config.PLAYER_FOCUS_FACTOR if focus else 1.0)
        self.player.vel = move * speed
        return focus

    # ------------------------------------------------------------------ #
    # 逻辑更新
    # ------------------------------------------------------------------ #
    def _spawn_bullets(self, dt: float) -> None:
        """按定时器生成子弹，采用环形弹幕以充分触发碰撞/擦弹判定。"""
        self.spawn_timer -= dt
        if self.spawn_timer > 0:
            return
        self.spawn_timer = 0.35

        cx = random.uniform(80, config.SCREEN_W - 80)
        cy = -10.0
        count = 12
        base_angle = math.radians(random.uniform(40, 140))
        for i in range(count):
            angle = base_angle + (i - count / 2) * math.radians(6)
            vx = math.cos(angle) * config.BULLET_SPEED
            vy = math.sin(angle) * config.BULLET_SPEED
            color = config.CYAN if i % 2 else config.RED
            self.bullets.append(Bullet(cx, cy, vx, vy, color=color))

    def _check_collisions(self) -> None:
        """双层判定：擦弹区（外层，不致命）/ 命中区（内层，致命）。

        宽相位用空间网格先把子弹按格分区，缩小精确检测的候选集；
        精确检测用线段-圆（扫掠），避免高速子弹穿模。
        """
        grid = collision.SpatialGrid(config.SCREEN_W, config.SCREEN_H,
                                     config.GRID_CELL_SIZE)
        for b in self.bullets:
            grid.insert(b, b.pos.x, b.pos.y)

        px, py = self.player.pos.x, self.player.pos.y
        for b in self.bullets:
            if not b.alive:
                continue

            # 宽相位：只取玩家附近的子弹
            if b not in grid.query(px, py, self.player.graze_radius + b.radius + 1):
                continue

            # 扫掠：上一帧位置 -> 当前位置 视为线段
            if collision.segment_circle(b.prev_pos.x, b.prev_pos.y,
                                        b.pos.x, b.pos.y,
                                        px, py, self.player.radius + b.radius):
                self._on_player_hit(b)
                continue

            # 未命中，再判擦弹
            if not b.grazed and collision.segment_circle(
                    b.prev_pos.x, b.prev_pos.y, b.pos.x, b.pos.y,
                    px, py, self.player.graze_radius + b.radius):
                b.grazed = True
                self.player.graze_count += 1
                self.graze_total += 1

    def _on_player_hit(self, bullet: Bullet) -> None:
        bullet.alive = False
        self.hit_total += 1
        self.hit_flash = 0.25
        # 骨架阶段：被击中不结束，重置位置并清空擦弹连击
        self.player.pos = Vector2(config.SCREEN_W / 2, config.SCREEN_H - 80)
        self.player.graze_count = 0

    def update(self, dt: float) -> None:
        if self.paused:
            return

        self._read_player_input()
        self.player.update(dt)

        # 限制在窗口内
        self.player.pos.x = max(0, min(config.SCREEN_W, self.player.pos.x))
        self.player.pos.y = max(0, min(config.SCREEN_H, self.player.pos.y))

        self._spawn_bullets(dt)
        for b in self.bullets:
            b.update(dt)
        self.bullets = [b for b in self.bullets if b.alive]

        self._check_collisions()

        if self.hit_flash > 0:
            self.hit_flash = max(0.0, self.hit_flash - dt)

    # ------------------------------------------------------------------ #
    # 渲染
    # ------------------------------------------------------------------ #
    def _render(self) -> None:
        self.screen.fill(config.BLACK)

        focus = self._read_player_input()
        self.player.draw(self.screen, focus=focus)
        for b in self.bullets:
            b.draw(self.screen)

        self._draw_hud()

        if self.hit_flash > 0:
            draw_translucent_circle(
                self.screen, config.RED,
                (self.player.pos.x, self.player.pos.y),
                int(config.PLAYER_GRAZE_RADIUS * 2), alpha=90,
            )

        if self.paused:
            self._draw_center_text("已暂停  (P / 空格 继续)", config.YELLOW)

    def _draw_hud(self) -> None:
        lines = [
            f"擦弹 Graze : {self.graze_total}",
            f"被命中 Hit : {self.hit_total}",
            f"子弹数     : {len(self.bullets)}",
            "方向键/WASD 移动  Shift 低速  P 暂停",
        ]
        y = 8
        for line in lines:
            surf = self.font.render(line, True, config.WHITE)
            self.screen.blit(surf, (8, y))
            y += 22

    def _draw_center_text(self, text: str, color) -> None:
        surf = self.font_big.render(text, True, color)
        rect = surf.get_rect(center=(config.SCREEN_W // 2, config.SCREEN_H // 2))
        self.screen.blit(surf, rect)

    # ------------------------------------------------------------------ #
    # 主循环
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(config.FPS) / 1000.0, config.MAX_DT)
            self._handle_events()
            self.update(dt)
            self._render()
            pygame.display.flip()
        pygame.quit()
