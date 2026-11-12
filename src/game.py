"""游戏主循环与场景逻辑。

采用「夹紧的时间步长」推进逻辑：每帧用 ``clock.tick`` 得到真实 elapsed，
并夹紧到 ``MAX_DT``，保证物理与碰撞在不同机器上表现一致，同时避免卡顿后穿模。
"""
from __future__ import annotations

import math

import pygame
from pygame.math import Vector2

from . import config, collision
from .entities import Boss, Bullet, Player, PlayerShot, draw_translucent_circle


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
        pygame.key.stop_text_input()
        pygame.display.set_caption("弹幕射击 - 碰撞检测 Demo")
        self.clock = pygame.time.Clock()
        self.font = _load_font(18)
        self.font_big = _load_font(30)

        self.running = True
        self.paused = False
        self.victory = False
        self.focus = False            # 是否处于低速（focus）状态，由 update 写入

        self.player = Player(config.SCREEN_W / 2, config.SCREEN_H - 80)
        self.boss = Boss(config.SCREEN_W / 2, config.BOSS_START_Y)
        self.bullets: list[Bullet] = []
        self.player_shots: list[PlayerShot] = []
        # 空间网格复用同一个实例，每帧 clear 后重新插入，避免反复新建
        self.grid = collision.SpatialGrid(config.SCREEN_W, config.SCREEN_H,
                                          config.GRID_CELL_SIZE)
        self.shooting = False
        self.shoot_requested = False
        self.fire_timer = 0.0
        self.boss_attack_timer = config.BOSS_PHASE1_INTERVAL
        self.boss_attack_phase = self.boss.phase
        self.graze_total = 0
        self.hit_total = 0
        self.hit_flash = 0.0          # 命中时的红屏闪烁计时

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
                elif event.key == pygame.K_r and self.victory:
                    self._reset_run()
                elif event.key == pygame.K_z:
                    self.shoot_requested = True
                elif event.key == pygame.K_F1:
                    self.paused = not self.paused

    def _read_player_input(self) -> tuple[bool, bool]:
        """读取玩家移动、低速和射击输入。"""
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
        shooting = bool(keys[pygame.K_z] or self.shoot_requested)
        return focus, shooting

    # ------------------------------------------------------------------ #
    # 逻辑更新
    # ------------------------------------------------------------------ #
    def _spawn_player_shots(self, dt: float) -> None:
        """按住射击键时按固定间隔发射玩家弹。"""
        self.fire_timer = max(0.0, self.fire_timer - dt)
        if self.shooting and self.fire_timer <= 0.0:
            self.player_shots.append(
                PlayerShot(self.player.pos.x, self.player.pos.y - self.player.radius)
            )
            self.fire_timer = config.PLAYER_FIRE_INTERVAL

    def _spawn_boss_attack(self) -> None:
        """按 Boss 阶段发射扇形瞄准弹或八方向环形弹。"""
        if self.boss.phase == 1:
            direction = self.player.pos - self.boss.pos
            if direction.length_squared() == 0:
                direction = Vector2(0.0, 1.0)
            base_angle = math.atan2(direction.y, direction.x)
            middle = (config.BOSS_FAN_COUNT - 1) / 2
            for i in range(config.BOSS_FAN_COUNT):
                offset = (i - middle) * math.radians(config.BOSS_FAN_STEP_DEGREES)
                angle = base_angle + offset
                color = config.CYAN if i % 2 else config.RED
                self.bullets.append(Bullet(
                    self.boss.pos.x,
                    self.boss.pos.y,
                    math.cos(angle) * config.BOSS_ATTACK_SPEED,
                    math.sin(angle) * config.BOSS_ATTACK_SPEED,
                    color=color,
                ))
            return

        for i in range(config.BOSS_RING_COUNT):
            angle = math.tau * i / config.BOSS_RING_COUNT
            self.bullets.append(Bullet(
                self.boss.pos.x,
                self.boss.pos.y,
                math.cos(angle) * config.BOSS_ATTACK_SPEED,
                math.sin(angle) * config.BOSS_ATTACK_SPEED,
                color=config.CYAN if i % 2 else config.RED,
            ))

    def _update_boss_attacks(self, dt: float) -> None:
        if not self.boss.alive:
            return

        phase = self.boss.phase
        interval = (config.BOSS_PHASE1_INTERVAL if phase == 1
                    else config.BOSS_PHASE2_INTERVAL)
        if phase != self.boss_attack_phase:
            self.boss_attack_phase = phase
            self.boss_attack_timer = interval

        self.boss_attack_timer -= dt
        if self.boss_attack_timer > 0.0:
            return

        self._spawn_boss_attack()
        self.boss_attack_timer = interval

    def _check_boss_collisions(self) -> None:
        """用相对运动线段检测玩家弹与移动 Boss 的碰撞。"""
        if self.boss.alive:
            for shot in self.player_shots:
                if not shot.alive:
                    continue
                x1 = shot.prev_pos.x - self.boss.prev_pos.x
                y1 = shot.prev_pos.y - self.boss.prev_pos.y
                x2 = shot.pos.x - self.boss.pos.x
                y2 = shot.pos.y - self.boss.pos.y
                if collision.segment_circle(
                        x1, y1, x2, y2, 0.0, 0.0,
                        shot.radius + self.boss.radius):
                    shot.alive = False
                    self.boss.take_damage(shot.damage)
                    if not self.boss.alive:
                        break

        self.player_shots = [shot for shot in self.player_shots if shot.alive]
        if not self.boss.alive:
            self.victory = True
            self.bullets.clear()
            self.player_shots.clear()

    def _reset_run(self) -> None:
        """重置玩家、Boss、弹幕、计时器与本局统计。"""
        self.player = Player(config.SCREEN_W / 2, config.SCREEN_H - 80)
        self.boss = Boss(config.SCREEN_W / 2, config.BOSS_START_Y)
        self.bullets.clear()
        self.player_shots.clear()
        self.grid.clear()
        self.shooting = False
        self.shoot_requested = False
        self.fire_timer = 0.0
        self.boss_attack_timer = config.BOSS_PHASE1_INTERVAL
        self.boss_attack_phase = self.boss.phase
        self.graze_total = 0
        self.hit_total = 0
        self.hit_flash = 0.0
        self.focus = False
        self.paused = False
        self.victory = False

    def _check_collisions(self) -> None:
        """双层判定：擦弹区（外层，不致命）/ 命中区（内层，致命）。

        宽相位：把子弹按格插入空间网格，只对玩家邻域格子内的候选子弹做精确检测，
        避免对所有子弹两两检测。
        精确检测：用线段-圆（扫掠）判定，把子弹一帧位移当作线段，防止高速穿模。
        """
        self.grid.clear()
        max_bullet_reach = 0.0
        for b in self.bullets:
            self.grid.insert(b, b.pos.x, b.pos.y)
            travel = b.pos.distance_to(b.prev_pos)
            max_bullet_reach = max(max_bullet_reach, b.radius + travel)

        px, py = self.player.pos.x, self.player.pos.y
        player_travel = self.player.pos.distance_to(self.player.prev_pos)
        # 将双方本帧位移和实际子弹半径纳入范围，确保扫掠命中的子弹不会被宽相位过滤。
        query_radius = self.player.graze_radius + player_travel + max_bullet_reach
        candidates = self.grid.query(px, py, query_radius)
        p0x, p0y = self.player.prev_pos.x, self.player.prev_pos.y
        for b in candidates:
            if not b.alive:
                continue

            # 转为相对运动：子弹上一帧相对玩家上一帧，至本帧相对位置。
            x1, y1 = b.prev_pos.x - p0x, b.prev_pos.y - p0y
            x2, y2 = b.pos.x - px, b.pos.y - py

            # 先判内层命中区，命中后直接跳过擦弹判定
            if collision.segment_circle(x1, y1, x2, y2, 0.0, 0.0,
                                        self.player.radius + b.radius):
                self._on_player_hit(b)
                continue

            # 未命中，再判外层擦弹区（每颗子弹只计一次）
            if not b.grazed and collision.segment_circle(
                    x1, y1, x2, y2, 0.0, 0.0,
                    self.player.graze_radius + b.radius):
                b.grazed = True
                self.player.graze_count += 1
                self.graze_total += 1

    def _on_player_hit(self, bullet: Bullet) -> None:
        bullet.alive = False
        self.hit_total += 1
        self.hit_flash = 0.25
        # 骨架阶段：被击中不结束，重置位置并清空擦弹连击
        self.player.pos = Vector2(config.SCREEN_W / 2, config.SCREEN_H - 80)
        self.player.prev_pos = Vector2(self.player.pos)
        self.player.graze_count = 0

    def update(self, dt: float) -> None:
        if self.paused or self.victory:
            self.shoot_requested = False
            return

        self.focus, self.shooting = self._read_player_input()
        self.player.update(dt)

        # 限制在窗口内
        self.player.pos.x = max(0, min(config.SCREEN_W, self.player.pos.x))
        self.player.pos.y = max(0, min(config.SCREEN_H, self.player.pos.y))

        if self.boss.alive:
            self.boss.update(dt)
        self._spawn_player_shots(dt)
        self.shoot_requested = False
        for shot in self.player_shots:
            shot.update(dt)
        self._check_boss_collisions()
        if self.victory:
            return

        self._update_boss_attacks(dt)
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

        self.boss.draw(self.screen)
        for shot in self.player_shots:
            if shot.alive:
                shot.draw(self.screen)
        self.player.draw(self.screen, focus=self.focus)
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
            self._draw_center_text("已暂停  (F1 继续)", config.YELLOW)
        elif self.victory:
            self._draw_center_text("Boss 击破！按 R 重新开始", config.YELLOW)

    def _draw_hud(self) -> None:
        bar = pygame.Rect(8, 8, config.SCREEN_W - 16, 12)
        pygame.draw.rect(self.screen, config.GRAY, bar)
        health_ratio = max(0.0, self.boss.hp / self.boss.max_hp)
        fill = bar.inflate(-4, -4)
        fill.width = round(fill.width * health_ratio)
        if fill.width > 0 and fill.height > 0:
            color = config.CYAN if self.boss.phase == 1 else config.RED
            pygame.draw.rect(self.screen, color, fill)
        pygame.draw.rect(self.screen, config.WHITE, bar, 1)

        lines = [
            f"Boss 阶段 {self.boss.phase}  擦弹 {self.graze_total}  命中 {self.hit_total}",
            f"敌弹数量 {len(self.bullets)}",
            "方向键/WASD 移动  Shift 低速  Z 点射/按住连发  F1 暂停",
        ]
        y = 26
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
