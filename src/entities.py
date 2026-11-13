"""游戏实体：玩家、Boss 与子弹。

所有实体继承 ``Entity``，统一 ``update(dt)`` / ``draw(surface)`` 接口。
与碰撞相关的两个半径定义在实体上（``radius`` 命中半径、
``graze_radius`` 擦弹半径），由 ``Game`` 统一做双层判定。
"""
from __future__ import annotations

import math

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

    def draw(
            self, surface: pygame.Surface, focus: bool = False,
            sprite: pygame.Surface | None = None) -> None:
        if sprite is not None:
            surface.blit(sprite, sprite.get_rect(center=self.pos))
            self._draw_focus_marker(surface, focus)
            return

        # 外层擦弹区（半透明），低速移动时更醒目
        draw_translucent_circle(
            surface, config.BLUE, (self.pos.x, self.pos.y),
            int(self.graze_radius), alpha=90 if focus else 45,
        )
        self._draw_focus_marker(surface, focus)

    def _draw_focus_marker(self, surface: pygame.Surface, focus: bool) -> None:
        """低速时突出显示命中判定点，便于在弹幕中定位。"""
        center = (round(self.pos.x), round(self.pos.y))
        if focus:
            pygame.draw.circle(surface, config.WHITE, center, 11, 2)
            pygame.draw.circle(
                surface, config.RED, center, max(2, round(self.radius)), 0
            )
        else:
            pygame.draw.circle(
                surface, config.WHITE, center, max(1, round(self.radius)), 0
            )


class Bullet(Entity):
    """敌方子弹。记录上一帧位置，供扫掠检测使用。"""

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 radius: float = config.BULLET_RADIUS,
                 color: tuple[int, int, int] = config.RED,
                 sprite: pygame.Surface | None = None) -> None:
        super().__init__(x, y)
        self.vel = Vector2(vx, vy)
        self.radius = radius
        self.color = color
        self.sprite = sprite        # 弹型贴图，为空时回退为程序绘制的圆
        self.prev_pos = Vector2(x, y)  # 上一帧位置
        self.grazed = False            # 每颗子弹只计一次擦弹

    def update(self, dt: float) -> None:
        self.prev_pos = Vector2(self.pos)
        super().update(dt)
        margin = 60
        if (
            self.pos.x < config.PLAYFIELD_LEFT - margin
            or self.pos.x > config.PLAYFIELD_RIGHT + margin
            or self.pos.y < config.PLAYFIELD_TOP - margin
            or self.pos.y > config.PLAYFIELD_BOTTOM + margin
        ):
            self.alive = False  # 出屏回收

    def draw(
            self, surface: pygame.Surface,
            sprite: pygame.Surface | None = None) -> None:
        image = self.sprite if self.sprite is not None else sprite
        if image is not None:
            surface.blit(image, image.get_rect(center=self.pos))
            return

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
        if self.pos.y < config.PLAYFIELD_TOP - self.radius:
            self.alive = False

    def draw(
            self, surface: pygame.Surface,
            sprite: pygame.Surface | None = None) -> None:
        if sprite is not None:
            surface.blit(sprite, sprite.get_rect(center=self.pos))
            return

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
        """按剩余生命值把整场战斗切成三段符卡。"""
        if self.hp <= self.max_hp / 3.0:
            return 3
        if self.hp <= self.max_hp * 2.0 / 3.0:
            return 2
        return 1

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

    def draw(
            self, surface: pygame.Surface,
            sprite: pygame.Surface | None = None) -> None:
        if sprite is not None:
            surface.blit(sprite, sprite.get_rect(center=self.pos))
            return

        center = (round(self.pos.x), round(self.pos.y))
        radius = int(self.radius)
        pygame.draw.circle(surface, config.RED, center, radius)
        pygame.draw.circle(surface, config.YELLOW, center, radius, 3)
        pygame.draw.circle(surface, config.WHITE, center, max(3, radius // 3))


class Fairy(Entity):
    """小妖精：从场地上方飘落，左右轻微摆动，可被玩家弹击破。

    被击破时由 ``Game`` 结算分数并掉落道具；出屏后自动回收。
    """

    def __init__(
        self, x: float, y: float, speed: float, sway: float,
        variant: bool = False,
    ) -> None:
        super().__init__(x, y)
        self.prev_pos = Vector2(self.pos)
        self.radius = config.FAIRY_RADIUS
        self.max_hp = config.FAIRY_HP
        self.hp = self.max_hp
        self.speed = speed
        self.sway = sway
        self.variant = variant
        self.phase = 0.0
        self.timer = 0.0
        self.hit_flash = 0.0        # 受击闪白计时

    def take_damage(self, amount: float) -> None:
        self.hp = max(0.0, self.hp - max(0.0, amount))
        self.alive = self.hp > 0.0

    def update(self, dt: float) -> None:
        self.prev_pos = Vector2(self.pos)
        self.timer += dt
        self.phase += dt
        self.hit_flash = max(0.0, self.hit_flash - dt)
        self.pos.y += self.speed * dt
        self.pos.x += math.sin(self.phase * 1.6) * self.sway * dt
        if self.pos.y > config.PLAYFIELD_BOTTOM + 60:
            self.alive = False

    def draw(
            self, surface: pygame.Surface,
            frames: tuple[pygame.Surface, ...] | None = None,
            flash: float = 0.0) -> None:
        if not frames:
            return
        image = frames[int(self.timer * 6) % len(frames)]
        if flash > 0.0:
            image = image.copy()
            value = max(0, min(255, round(255 * flash)))
            image.fill((value, value, value, 0),
                       special_flags=pygame.BLEND_RGBA_ADD)
        surface.blit(image, image.get_rect(center=self.pos))


class Item(Entity):
    """掉落道具：匀速下落，进入自机吸附范围后被磁吸，出屏回收。

    ``kind`` 取 ``config.ITEM_KINDS``（power / point / life），决定外观与
    拾取效果；本实体只负责运动与回收，效果由 ``Game`` 处理。
    """

    def __init__(self, x: float, y: float, kind: str,
                 sprite: pygame.Surface | None = None) -> None:
        super().__init__(x, y)
        self.kind = kind
        self.radius = config.ITEM_RADIUS
        self.vel = Vector2(0.0, config.ITEM_FALL_SPEED)
        self.sprite = sprite
        self.timer = 0.0

    def update(self, dt: float) -> None:
        """按 ``vel`` 移动；磁吸方向由 ``Game`` 每帧写入。"""
        self.timer += dt
        super().update(dt)
        if self.pos.y > config.PLAYFIELD_BOTTOM + 40.0:
            self.alive = False

    def draw(
            self, surface: pygame.Surface,
            halo: pygame.Surface | None = None) -> None:
        # 光环随计时器脉动透明度，把道具与普通子弹区分开
        if halo is not None:
            frame = halo.copy()
            frame.set_alpha(
                round(120 + 90 * (0.5 + 0.5 * math.sin(self.timer * 7.0)))
            )
            surface.blit(frame, frame.get_rect(center=self.pos))
        if self.sprite is not None:
            surface.blit(self.sprite, self.sprite.get_rect(center=self.pos))
            return
        pygame.draw.circle(
            surface, config.ITEM_KIND_COLORS.get(self.kind, config.WHITE),
            (round(self.pos.x), round(self.pos.y)), max(1, round(self.radius)),
        )


class Effect:
    """一次性特效：贴图从起始缩放扩散并淡出，播完自动消失。

    不参与碰撞，只推进自身计时器，供渲染层做帧动画。
    """

    def __init__(self, x: float, y: float, image: pygame.Surface, duration: float,
                 start_scale: float = 0.5, end_scale: float = 1.2,
                 start_alpha: int = 255, end_alpha: int = 0) -> None:
        self.pos = Vector2(x, y)
        self.image = image
        self.duration = duration
        self.timer = 0.0
        self.start_scale = start_scale
        self.end_scale = end_scale
        self.start_alpha = start_alpha
        self.end_alpha = end_alpha

    @property
    def alive(self) -> bool:
        return self.timer < self.duration

    def update(self, dt: float) -> None:
        self.timer += dt

    def draw(self, surface: pygame.Surface) -> None:
        progress = min(1.0, self.timer / self.duration)
        scale = self.start_scale + (self.end_scale - self.start_scale) * progress
        frame = pygame.transform.smoothscale(
            self.image,
            (max(1, round(self.image.get_width() * scale)),
             max(1, round(self.image.get_height() * scale))),
        )
        frame.set_alpha(
            round(self.start_alpha + (self.end_alpha - self.start_alpha) * progress)
        )
        surface.blit(frame, frame.get_rect(center=self.pos))
