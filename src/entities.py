"""游戏实体：玩家、Boss 与子弹。

所有实体继承 ``Entity``，统一 ``update(dt)`` / ``draw(surface)`` 接口。
与碰撞相关的两个半径定义在实体上（``radius`` 命中半径、
``graze_radius`` 擦弹半径），由 ``Game`` 统一做双层判定。
"""
from __future__ import annotations

import pygame
from pygame.math import Vector2

from . import config


_OVERLAY_CACHE: dict[tuple, pygame.Surface] = {}


def draw_translucent_circle(surface: pygame.Surface, color: tuple[int, int, int],
                            center: tuple[float, float], radius: int,
                            alpha: int = 60) -> None:
    """在 surface 上叠加一个半透明圆。

    半透明圆需借助带 alpha 的临时表面实现，这里按 (颜色, 半径, alpha) 缓存，
    避免每帧重复创建 Surface。
    """
    key = (color, radius, alpha)
    overlay = _OVERLAY_CACHE.get(key)
    if overlay is None:
        overlay = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(overlay, (*color, alpha), (radius, radius), radius)
        _OVERLAY_CACHE[key] = overlay
    surface.blit(overlay, (center[0] - radius, center[1] - radius))


class Entity:
    """实体基类：位置、速度、命中半径与存活标记。"""

    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        self.pos = Vector2(x, y)
        self.vel = Vector2(0.0, 0.0)
        self.radius = 0.0
        self.alive = True

    def update(self, dt: float) -> None:
        self.pos += self.vel * dt

    def draw(self, surface: pygame.Surface) -> None:  # pragma: no cover - 抽象接口
        raise NotImplementedError


class Player(Entity):
    """自机。命中半径极小，擦弹半径较大，用于展示双层判定。"""

    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y)
        self.prev_pos = Vector2(self.pos)
        self.radius = config.PLAYER_HIT_RADIUS
        self.graze_radius = config.PLAYER_GRAZE_RADIUS
        self.graze_count = 0

    def update(self, dt: float) -> None:
        self.prev_pos = Vector2(self.pos)
        super().update(dt)

    def draw(self, surface: pygame.Surface, focus: bool = False) -> None:
        # 外层擦弹区（半透明），低速移动时更醒目
        draw_translucent_circle(
            surface, config.BLUE, (self.pos.x, self.pos.y),
            int(self.graze_radius), alpha=90 if focus else 45,
        )
        # 中心命中区（实心小圆）
        pygame.draw.circle(surface, config.WHITE,
                           (int(self.pos.x), int(self.pos.y)),
                           int(self.radius) + 2)


class Bullet(Entity):
    """敌方子弹。记录上一帧位置，供扫掠检测使用。"""

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 radius: float = config.BULLET_RADIUS,
                 color: tuple[int, int, int] = config.RED) -> None:
        super().__init__(x, y)
        self.vel = Vector2(vx, vy)
        self.radius = radius
        self.color = color
        self.prev_pos = Vector2(x, y)  # 上一帧位置
        self.grazed = False            # 每颗子弹只计一次擦弹

    def update(self, dt: float) -> None:
        self.prev_pos = Vector2(self.pos)
        super().update(dt)
        margin = 60
        if (self.pos.x < -margin or self.pos.x > config.SCREEN_W + margin or
                self.pos.y < -margin or self.pos.y > config.SCREEN_H + margin):
            self.alive = False  # 出屏回收

    def draw(self, surface: pygame.Surface) -> None:
        center = (int(self.pos.x), int(self.pos.y))
        r = int(self.radius)
        pygame.draw.circle(surface, self.color, center, r)
        pygame.draw.circle(surface, config.WHITE, center, max(1, r // 2))


class PlayerShot(Entity):
    """玩家射出的直线弹，保留上一帧位置供连续碰撞检测。"""

    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y)
        self.vel = Vector2(0.0, -config.PLAYER_SHOT_SPEED)
        self.radius = config.PLAYER_SHOT_RADIUS
        self.damage = config.PLAYER_SHOT_DAMAGE
        self.prev_pos = Vector2(self.pos)

    def update(self, dt: float) -> None:
        self.prev_pos = Vector2(self.pos)
        super().update(dt)
        if self.pos.y < -self.radius:
            self.alive = False

    def draw(self, surface: pygame.Surface) -> None:
        width = max(2, int(self.radius * 2))
        height = max(4, int(self.radius * 4))
        rect = pygame.Rect(0, 0, width, height)
        rect.center = (round(self.pos.x), round(self.pos.y))
        pygame.draw.ellipse(surface, config.CYAN, rect)


class Boss(Entity):
    """单关 Boss：水平往返移动，以剩余生命值切换攻击阶段。"""

    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y)
        self.prev_pos = Vector2(self.pos)
        self.radius = config.BOSS_RADIUS
        self.max_hp = config.BOSS_MAX_HP
        self.hp = self.max_hp
        self.direction = 1

    @property
    def phase(self) -> int:
        return 2 if self.hp <= self.max_hp / 2 else 1

    def take_damage(self, amount: float) -> None:
        self.hp = max(0.0, self.hp - max(0.0, amount))
        self.alive = self.hp > 0.0

    def update(self, dt: float) -> None:
        self.prev_pos = Vector2(self.pos)
        self.pos.x += self.direction * config.BOSS_MOVE_SPEED * dt

        if self.pos.x <= config.BOSS_LEFT_BOUND:
            self.pos.x = config.BOSS_LEFT_BOUND
            self.direction = 1
        elif self.pos.x >= config.BOSS_RIGHT_BOUND:
            self.pos.x = config.BOSS_RIGHT_BOUND
            self.direction = -1

    def draw(self, surface: pygame.Surface) -> None:
        center = (round(self.pos.x), round(self.pos.y))
        radius = int(self.radius)
        pygame.draw.circle(surface, config.RED, center, radius)
        pygame.draw.circle(surface, config.YELLOW, center, radius, 3)
        pygame.draw.circle(surface, config.WHITE, center, max(3, radius // 3))
