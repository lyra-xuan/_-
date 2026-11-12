"""游戏主循环与场景逻辑。

采用「夹紧的时间步长」推进逻辑：每帧用 ``clock.tick`` 得到真实 elapsed，
并夹紧到 ``MAX_DT``，保证物理与碰撞在不同机器上表现一致，同时避免卡顿后穿模。
"""
from __future__ import annotations

import math
from pathlib import Path

import pygame
from pygame.math import Vector2

from . import config, collision
from .art import GameArt
from .entities import Boss, Bullet, Player, PlayerShot


def _load_font(size: int) -> pygame.font.Font:
    """按优先级挑选一个能显示中文的系统字体。"""
    for name in ("simsun", "nsimsun", "microsoftyahei", "simhei"):
        path = pygame.font.match_font(name)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


class Game:
    """游戏主体：窗口、主循环、输入、碰撞与渲染。"""

    SCENE_TITLE = "title"
    SCENE_CONTROLS = "controls"
    SCENE_PLAYING = "playing"
    MENU_ITEMS = ("开始游戏", "操作说明", "退出游戏")

    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((config.SCREEN_W, config.SCREEN_H))
        pygame.key.stop_text_input()
        pygame.display.set_caption("弹幕射击 - 碰撞检测 Demo")
        self.clock = pygame.time.Clock()
        self.font = _load_font(24)
        self.font_big = _load_font(42)
        self.art = GameArt()
        asset_dir = Path(__file__).resolve().parent.parent / "assets" / "title"
        title_background = pygame.image.load(
            str(asset_dir / "touhou-th06-title.jpg")
        )
        self.title_background = pygame.transform.smoothscale(
            title_background, (config.SCREEN_W, config.SCREEN_H)
        )
        self.title_shade = pygame.Surface(
            (config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA
        )
        self.title_shade.fill((7, 3, 9, 112))

        menu_atlas = pygame.image.load(str(asset_dir / "project-striker-menu.webp"))
        self.title_menu_images = tuple(
            tuple(
                pygame.transform.smoothscale(
                    menu_atlas.subsurface((column * 256, row * 64, 256, 64)),
                    (360, 90),
                )
                for column in (0, 1)
            )
            for row in (0, 3, 5)
        )

        self.running = True
        self.scene = self.SCENE_TITLE
        self.menu_selection = 0
        self.paused = False
        self.victory = False
        self.game_over = False
        self.lives = config.PLAYER_LIVES
        self.invulnerable_timer = 0.0
        self.focus = False            # 是否处于低速（focus）状态，由 update 写入

        self.player = Player(
            config.PLAYER_START_X, config.PLAYER_START_Y
        )
        self.boss = Boss(config.BOSS_START_X, config.BOSS_START_Y)
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
        self.animation_timer = 0.0
        self.playfield_shade = pygame.Surface(
            (config.PLAYFIELD_WIDTH, config.PLAYFIELD_HEIGHT), pygame.SRCALPHA
        )
        self.playfield_shade.fill((7, 3, 9, 52))
        self.panel_shade = pygame.Surface(
            (416, config.PLAYFIELD_HEIGHT), pygame.SRCALPHA
        )
        self.panel_shade.fill((*config.PANEL, 222))
        self.hit_overlay = pygame.Surface(
            (config.PLAYFIELD_WIDTH, config.PLAYFIELD_HEIGHT), pygame.SRCALPHA
        )
        self.hit_overlay.fill((150, 12, 30, 80))

    # ------------------------------------------------------------------ #
    # 输入
    # ------------------------------------------------------------------ #
    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(event.key)

    def _handle_keydown(self, key: int) -> None:
        if self.scene == self.SCENE_TITLE:
            if key == pygame.K_UP:
                self.menu_selection = (self.menu_selection - 1) % len(self.MENU_ITEMS)
            elif key == pygame.K_DOWN:
                self.menu_selection = (self.menu_selection + 1) % len(self.MENU_ITEMS)
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.menu_selection == 0:
                    self._reset_run()
                    self.scene = self.SCENE_PLAYING
                elif self.menu_selection == 1:
                    self.scene = self.SCENE_CONTROLS
                else:
                    self.running = False
            elif key == pygame.K_ESCAPE:
                self.running = False
            return

        if self.scene == self.SCENE_CONTROLS:
            if key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
                self.scene = self.SCENE_TITLE
            return

        if self.game_over:
            if key == pygame.K_r:
                self._reset_run()
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                self.game_over = False
                self.scene = self.SCENE_TITLE
                self.menu_selection = 0
            return

        if key == pygame.K_ESCAPE:
            self.running = False
        elif key == pygame.K_r and self.victory:
            self._reset_run()
        elif key == pygame.K_z:
            self.shoot_requested = True
        elif key == pygame.K_F1:
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
        self.player = Player(config.PLAYER_START_X, config.PLAYER_START_Y)
        self.boss = Boss(config.BOSS_START_X, config.BOSS_START_Y)
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
        self.lives = config.PLAYER_LIVES
        self.invulnerable_timer = 0.0
        self.focus = False
        self.paused = False
        self.victory = False
        self.game_over = False
        self.scene = self.SCENE_PLAYING
        self.animation_timer = 0.0

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
            if not b.alive or self.invulnerable_timer > 0.0:
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
        if self.invulnerable_timer > 0.0 or self.game_over:
            return

        bullet.alive = False
        self.hit_total += 1
        self.hit_flash = 0.25
        self.lives -= 1
        self.bullets.clear()
        self.player.pos = Vector2(config.PLAYER_START_X, config.PLAYER_START_Y)
        self.player.prev_pos = Vector2(self.player.pos)
        self.player.graze_count = 0
        if self.lives <= 0:
            self.lives = 0
            self.game_over = True
            self.invulnerable_timer = 0.0
            self.hit_flash = 0.0
            self.player_shots.clear()
            self.shooting = False
        else:
            self.invulnerable_timer = config.PLAYER_INVULNERABLE_TIME

    def update(self, dt: float) -> None:
        if self.scene != self.SCENE_PLAYING:
            return
        if self.paused or self.victory or self.game_over:
            self.shoot_requested = False
            return

        self.invulnerable_timer = max(0.0, self.invulnerable_timer - dt)
        self.focus, self.shooting = self._read_player_input()
        self.player.update(dt)

        # 限制在窗口内
        self.player.pos.x = max(
            config.PLAYFIELD_LEFT + self.player.radius,
            min(config.PLAYFIELD_RIGHT - self.player.radius, self.player.pos.x),
        )
        self.player.pos.y = max(
            config.PLAYFIELD_TOP + self.player.radius,
            min(config.PLAYFIELD_BOTTOM - self.player.radius, self.player.pos.y),
        )
        self.animation_timer += dt

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
        if self.scene == self.SCENE_TITLE:
            self._draw_title_screen()
            return
        if self.scene == self.SCENE_CONTROLS:
            self._draw_controls_screen()
            return

        field_origin = (config.PLAYFIELD_LEFT, config.PLAYFIELD_TOP)
        self.screen.blit(self.art.scene_background, (0, 0))
        self.screen.blit(self.art.playfield_background, field_origin)
        self.screen.blit(self.playfield_shade, field_origin)

        self.boss.draw(self.screen, self.art.boss_portrait)
        for shot in self.player_shots:
            if shot.alive:
                shot.draw(self.screen, self.art.player_shot)
        blinking = (
            self.invulnerable_timer > 0.0
            and int(self.invulnerable_timer * 12) % 2 == 0
        )
        if not blinking:
            frame = int(self.animation_timer * 8) % len(self.art.player_frames)
            self.player.draw(
                self.screen,
                focus=self.focus,
                sprite=self.art.player_frames[frame],
            )
        for b in self.bullets:
            b.draw(
                self.screen,
                self.art.enemy_bullet_sprites.get(
                    b.color, self.art.enemy_bullet_sprites[config.RED]
                ),
            )

        if self.hit_flash > 0:
            self.hit_overlay.set_alpha(round(90 * self.hit_flash / 0.25))
            self.screen.blit(self.hit_overlay, field_origin)

        self._draw_hud()

        if self.paused:
            self._draw_center_text("已暂停  (F1 继续)", config.PALE_GOLD)
        elif self.game_over:
            center_y = config.PLAYFIELD_TOP + config.PLAYFIELD_HEIGHT // 2
            self._draw_center_text("游戏失败", config.PALE_GOLD)
            self._draw_center_text(
                "R 重新开始 · Enter / Esc 返回标题",
                config.PALE_GOLD,
                font=self.font,
                y=center_y + 48,
            )
        elif self.victory:
            self._draw_center_text("Boss 击破！按 R 重新开始", config.PALE_GOLD)

    def _draw_title_screen(self) -> None:
        self.screen.blit(self.title_background, (0, 0))
        self.screen.blit(self.title_shade, (0, 0))
        self.screen.blit(
            self.font_big.render("星河弹幕", True, config.PALE_GOLD),
            (88, 115),
        )
        self.screen.blit(
            self.font.render("单关弹幕射击 · 碰撞检测实践", True, config.WHITE),
            (96, 180),
        )
        self.screen.blit(
            self.font.render("方向键选择    Enter 确认", True, config.WHITE),
            (800, 425),
        )

        for index, (selected_image, idle_image) in enumerate(self.title_menu_images):
            image = selected_image if index == self.menu_selection else idle_image
            self.screen.blit(image, (800, 500 + index * 112))

    def _draw_controls_screen(self) -> None:
        self.screen.blit(self.title_background, (0, 0))
        self.screen.blit(self.title_shade, (0, 0))
        self.screen.blit(
            self.font_big.render("操作说明", True, config.PALE_GOLD),
            (110, 118),
        )
        self.screen.blit(
            self.font.render("Enter / Esc 返回标题页", True, config.WHITE),
            (820, 150),
        )

        rows = (
            ("方向键 / WASD", "移动"),
            ("Shift", "低速移动，便于躲避弹幕"),
            ("Z", "点按单发，按住连续射击"),
            ("F1", "暂停或继续"),
            ("R", "胜利或失败后重新开始"),
            ("Enter / Esc", "失败后返回标题页"),
            ("Esc", "战斗时退出游戏"),
        )
        for index, (key, action) in enumerate(rows):
            y = 330 + index * 72
            self.screen.blit(self.font.render(key, True, config.PALE_GOLD), (110, y))
            self.screen.blit(
                self.font.render(action, True, config.WHITE),
                (900, y),
            )

    def _draw_text_centered(
            self, text: str, y: int, color, font: pygame.font.Font) -> None:
        surface = font.render(text, True, color)
        center_x = config.PLAYFIELD_LEFT + config.PLAYFIELD_WIDTH // 2
        rect = surface.get_rect(center=(center_x, y))
        self.screen.blit(surface, rect)

    def _draw_hud(self) -> None:
        panel = pygame.Rect(
            config.PLAYFIELD_RIGHT + 32,
            config.PLAYFIELD_TOP,
            config.SCREEN_W - config.PLAYFIELD_RIGHT - 64,
            config.PLAYFIELD_HEIGHT,
        )
        self.screen.blit(self.panel_shade, panel.topleft)
        pygame.draw.rect(self.screen, config.GOLD, panel, 2)
        field = pygame.Rect(
            config.PLAYFIELD_LEFT,
            config.PLAYFIELD_TOP,
            config.PLAYFIELD_WIDTH,
            config.PLAYFIELD_HEIGHT,
        )
        pygame.draw.rect(self.screen, config.GOLD, field, 2)
        pygame.draw.line(
            self.screen, config.GOLD,
            (config.PLAYFIELD_RIGHT + 16, config.PLAYFIELD_TOP + 24),
            (config.PLAYFIELD_RIGHT + 16, config.PLAYFIELD_BOTTOM - 24),
            1,
        )

        left = panel.left + 24
        right = panel.right - 24
        self.screen.blit(
            self.font_big.render("红魔馆", True, config.PALE_GOLD),
            (left, panel.top + 28),
        )
        self.screen.blit(
            self.font.render("SCARLET DEVIL MANOR", True, config.MUTED),
            (left + 2, panel.top + 84),
        )
        pygame.draw.line(
            self.screen, config.GOLD,
            (left, panel.top + 132), (right, panel.top + 132), 1,
        )

        self.screen.blit(
            self.font.render("BOSS  /  PHASE", True, config.PALE_GOLD),
            (left, panel.top + 164),
        )
        self.screen.blit(
            self.font_big.render(str(self.boss.phase), True, config.WHITE),
            (left, panel.top + 197),
        )
        self.screen.blit(
            self.art.boss_portrait,
            (right - self.art.boss_portrait.get_width(), panel.top + 150),
        )

        health_ratio = max(0.0, self.boss.hp / self.boss.max_hp)
        self.screen.blit(
            self.font.render("生命值  /  HP", True, config.MUTED),
            (left, panel.top + 260),
        )
        health_bar = pygame.Rect(left, panel.top + 284, panel.width - 48, 18)
        pygame.draw.rect(self.screen, (47, 19, 28), health_bar)
        fill = health_bar.inflate(-4, -4)
        fill.width = round(fill.width * health_ratio)
        if fill.width > 0:
            pygame.draw.rect(self.screen, config.RED, fill)
        pygame.draw.rect(self.screen, config.GOLD, health_bar, 1)
        pygame.draw.line(
            self.screen, config.GOLD,
            (left, panel.top + 334), (right, panel.top + 334), 1,
        )

        self.screen.blit(
            self.font.render("残机  /  LIVES", True, config.PALE_GOLD),
            (left, panel.top + 365),
        )
        icon_y = panel.top + 353
        icon_x = right - 94
        for index in range(config.PLAYER_LIVES):
            icon = self.art.player_icon.copy()
            icon.set_alpha(255 if index < self.lives else 60)
            self.screen.blit(icon, (icon_x + index * 30, icon_y))

        rows = (
            ("擦弹  /  GRAZE", self.graze_total),
            ("命中  /  HITS", self.hit_total),
            ("敌弹  /  BULLETS", len(self.bullets)),
        )
        for index, (label, value) in enumerate(rows):
            y = panel.top + 447 + index * 68
            self.screen.blit(self.font.render(label, True, config.MUTED), (left, y))
            value_surface = self.font.render(str(value), True, config.WHITE)
            self.screen.blit(value_surface, value_surface.get_rect(topright=(right, y)))

        divider_y = panel.top + 668
        pygame.draw.line(
            self.screen, config.GOLD,
            (left, divider_y), (right, divider_y), 1,
        )
        self.screen.blit(
            self.font.render("操  作  /  CONTROL", True, config.PALE_GOLD),
            (left, divider_y + 30),
        )
        hints = ("方向键 / WASD   移动", "Shift   低速", "Z   射击        F1   暂停")
        for index, hint in enumerate(hints):
            self.screen.blit(
                self.font.render(hint, True, config.WHITE),
                (left, divider_y + 76 + index * 42),
            )

    def _draw_center_text(
            self, text: str, color, font: pygame.font.Font | None = None,
            y: int | None = None) -> None:
        font = font or self.font_big
        surf = font.render(text, True, color)
        center = (
            config.PLAYFIELD_LEFT + config.PLAYFIELD_WIDTH // 2,
            y or config.PLAYFIELD_TOP + config.PLAYFIELD_HEIGHT // 2,
        )
        shadow = font.render(text, True, config.BLACK)
        self.screen.blit(shadow, shadow.get_rect(center=(center[0] + 2, center[1] + 2)))
        rect = surf.get_rect(center=center)
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
