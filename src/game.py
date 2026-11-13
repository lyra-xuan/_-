"""游戏主循环与场景逻辑。

采用「夹紧的时间步长」推进逻辑：每帧用 ``clock.tick`` 得到真实 elapsed，
并夹紧到 ``MAX_DT``，保证物理与碰撞在不同机器上表现一致，同时避免卡顿后穿模。
"""
from __future__ import annotations

import math
import random
from pathlib import Path

import pygame
from pygame.math import Vector2

from . import config, collision
from .art import GameArt
from .audio import Audio
from .entities import Boss, Bullet, Effect, Fairy, Item, Player, PlayerShot


def _load_font(size: int) -> pygame.font.Font:
    """按优先级挑选一个能显示中文的系统字体。"""
    for name in ("simsun", "nsimsun", "microsoftyahei", "simhei"):
        path = pygame.font.match_font(name)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


def _build_vignette(size: tuple[int, int]) -> pygame.Surface:
    """生成径向暗角：中心透明、边缘压暗，把视线收拢到弹幕场中央。

    从最大半径往中心逐层绘制更小、更透明的圆，后画的盖住先画的。
    """
    width, height = size
    overlay = pygame.Surface(size, pygame.SRCALPHA)
    center = (width // 2, height // 2)
    max_radius = math.hypot(width, height) / 2
    steps = 64
    for step in range(steps):
        ratio = step / steps
        radius = max_radius * (1.0 - ratio)
        alpha = int(config.VIGNETTE_MAX_ALPHA * (1.0 - ratio) ** 2)
        pygame.draw.circle(
            overlay, (*config.VIGNETTE_COLOR, alpha), center, int(radius)
        )
    return overlay


def _flash_sprite(sprite: pygame.Surface, amount: float) -> pygame.Surface:
    """把贴图整体加亮，用于 Boss 受击闪白；alpha 通道保持不变。"""
    frame = sprite.copy()
    value = max(0, min(255, round(255 * amount)))
    frame.fill((value, value, value, 0), special_flags=pygame.BLEND_RGBA_ADD)
    return frame


def _hiscore_path() -> Path:
    return Path(__file__).resolve().parent.parent / config.HISCORE_FILE


def _load_hiscore() -> int:
    try:
        return max(0, int(_hiscore_path().read_text(encoding="utf-8").strip()))
    except (OSError, ValueError):
        return 0


def _save_hiscore(value: int) -> None:
    try:
        _hiscore_path().write_text(str(value), encoding="utf-8")
    except OSError:
        pass       # 无写权限时静默忽略，不影响游戏


class Game:
    """游戏主体：窗口、主循环、输入、碰撞与渲染。"""

    SCENE_TITLE = "title"
    SCENE_CONTROLS = "controls"
    SCENE_PLAYING = "playing"
    ENDING_PAGES = ("result", "afterword", "credits")
    TITLE_INFO_PANEL_RECT = (52, 52, 500, 360)
    MENU_ITEMS = ("开始游戏", "操作说明", "退出游戏")
    ENTRY_CARD_DURATION = 1.8
    # 说明书分三页：背景 → 用语 → 操作
    MANUAL_PAGES = ("背景说明", "用语解说", "操作指南")

    # 页面一正文：缩进用全角空格，空串表示分段
    MANUAL_STORY = (
        "　　幻想乡，是被遗忘之物栖居的边境之地。",
        "",
        "　　然而这一年的夏天，红雾自湖畔升起。那不是寻常的晚霞，",
        "　而是浓得化不开的绯色，连满月也被浸成血红。人里的灯火",
        "　在雾中熄灭，夜长得望不见尽头。",
        "",
        "　　博丽的巫女再也坐不住。她循着雾的源头飞向湖心，",
        "　在红雾最浓处，望见一座矗立湖畔的洋馆——红魔馆。",
        "",
        "　　馆中住着活了五百年的吸血鬼，蕾米莉亚·史卡雷特。",
        "　她兴致勃勃地铺开漫天符卡——因为于她而言，",
        "　弹幕是比言语更诚实的问候。",
        "",
        "　　躲开绯红的弹雨，穿过三重符卡，",
        "　把这位任性的吸血鬼，从漫长的夜里唤醒吧。",
    )

    # 页面二：世界观与玩法术语
    MANUAL_TERMS = (
        ("幻想乡", "被遗忘之物栖居的边境之地，本作的舞台"),
        ("博丽的巫女", "异变退治者，也就是玩家操纵的自机"),
        ("红魔馆", "矗立湖畔的洋馆，吸血鬼蕾米莉亚的居所"),
        ("符卡 · Spell Card", "东方独有的弹幕规则，一张符卡即一段弹幕式样"),
        ("红符 / 红魔法 / 神枪", "蕾米莉亚三重符卡的类别名，对应三个战斗阶段"),
        ("弹幕", "符卡铺开的子弹群，全数躲开即为破符"),
        ("自机", "玩家操纵的角色"),
        ("残机", "剩余生命数，本作 3 条，受击减一"),
        ("判定点", "自机唯一的受击点，低速时可见"),
        ("擦弹 · Graze", "敌弹擦过判定点外圈未被击中，可得分"),
        ("红玉 · POWER", "PWR 标记；火力 +0.05，妖精轮换或 Boss 转阶段掉落"),
        ("青玉 · POINT", "PTS 标记；得分 +500，是妖精最常见的掉落"),
        ("绿玉 · LIFE", "1UP 标记；残机 +1，稀有妖精或第三符卡掉落"),
    )

    # 页面三：按键表
    MANUAL_KEYS = (
        ("方向键 / WASD", "移动自机"),
        ("Shift", "低速移动，判定点收缩，便于穿过弹缝"),
        ("Z", "点按单发，按住连续射击"),
        ("F1", "暂停 / 继续"),
        ("F2", "开关碰撞调试层（判定圆、扫掠线、空间网格）"),
        ("F3", "作弊模式：角色无敌（再次按下关闭）"),
        ("R", "胜负结算后重新开始"),
        ("胜利后 ← / →", "翻阅战绩、后记与鸣谢"),
        ("Enter", "胜利后翻页/结束阅读；失败后返回标题"),
        ("Esc", "返回标题；战斗中退出游戏"),
    )
    VICTORY_AFTERWORD = (
        "紅霧散去，滿月重新照亮了湖面。",
        "蕾米莉亞仍說，這不過是一場稍有趣味的遊戲。",
        "咲夜默默收拾彈痕與碎裂的窗玻璃，",
        "又替主人端來一杯溫熱的紅茶。",
        "",
        "博麗的巫女沒有收下謝禮，只確認人里的燈火",
        "已重新亮起，便乘風回到神社。",
        "",
        "數日之後，紅魔館再度傳出彈幕的聲響。",
        "幻想鄉的異変，大概從來不曾真正完結。",
    )
    VICTORY_CREDITS = (
        ("原作", "東方Project / 上海アリス幻樂団"),
        ("音乐", "Peaceful Romancer / ZUN"),
        ("曲目来源", "《东方怪绮谈》FM86 原曲"),
        ("素材", "東方紅魔郷（TH06）原作素材"),
        ("制作", "lyra"),
    )
    VICTORY_THANKS = (
        "そして、最後まで遊んでくれた貴方へ。",
        "ありがとう。",
    )

    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((config.SCREEN_W, config.SCREEN_H))
        pygame.key.stop_text_input()
        pygame.display.set_caption("弹幕射击 - 碰撞检测 Demo")
        self.clock = pygame.time.Clock()
        self.font = _load_font(24)
        self.font_big = _load_font(42)
        self.art = GameArt()
        self.audio = Audio()
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
        self.entry_shade = pygame.Surface(
            (config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA
        )
        self.entry_shade.fill((5, 2, 8, 168))
        self.ending_shade = pygame.Surface(
            (config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA
        )
        self.ending_shade.fill((7, 3, 9, 168))

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
        self.manual_page = 0          # 说明书当前页：背景 / 用语 / 操作
        self.ending_page = 0
        self.entry_card_timer = 0.0
        self.paused = False
        self.god_mode = False
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
        self.fairies: list[Fairy] = []
        self.fairy_kill_count = 0
        self.items: list[Item] = []
        self.fairy_timer = config.FAIRY_SPAWN_MIN
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
        self.debug_overlay = config.DEBUG_OVERLAY_DEFAULT
        self.debug_stats = self._empty_debug_stats()

        # 计分与战斗节奏
        self.score = 0
        self.hiscore = _load_hiscore()
        self.power = config.PLAYER_POWER_START   # 火力：决定自机弹幕密度
        self.item_total = 0                       # 本局已拾取道具数
        self.spiral_angle = 0.0                   # 阶段 3 螺旋弹幕的旋转相位
        self.effects: list[Effect] = []
        self.phase_timer = config.BOSS_PHASE_TIME_LIMIT
        self.boss_flash = 0.0            # Boss 受击闪白计时
        self.graze_fx_cooldown = 0.0     # 擦弹特效的节流，避免刷屏
        self.field_vignette = _build_vignette(
            (config.PLAYFIELD_WIDTH, config.PLAYFIELD_HEIGHT)
        )

    @staticmethod
    def _empty_debug_stats() -> dict[str, int]:
        """当帧碰撞统计，供调试层显示；每帧开始时清零。"""
        return {
            "candidates": 0,   # 宽相位候选数
            "sweeps": 0,       # 玩家弹参与扫掠的次数
            "hits": 0,         # 玩家被命中次数
            "grazes": 0,       # 本帧新增擦弹次数
            "boss_sweeps": 0,  # 玩家弹对 Boss 的扫掠次数
            "boss_hits": 0,    # 玩家弹命中 Boss 次数
        }

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
                self.audio.play("menu_move")
            elif key == pygame.K_DOWN:
                self.menu_selection = (self.menu_selection + 1) % len(self.MENU_ITEMS)
                self.audio.play("menu_move")
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.audio.play("menu_ok")
                if self.menu_selection == 0:
                    self._reset_run()
                    self.scene = self.SCENE_PLAYING
                elif self.menu_selection == 1:
                    self.manual_page = 0
                    self.scene = self.SCENE_CONTROLS
                else:
                    self.running = False
            elif key == pygame.K_ESCAPE:
                self.audio.play("menu_cancel")
                self.running = False
            return

        if self.scene == self.SCENE_CONTROLS:
            if key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
                self.audio.play("menu_cancel")
                self.scene = self.SCENE_TITLE
            elif key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
                step = -1 if key in (pygame.K_LEFT, pygame.K_a) else 1
                page = min(max(self.manual_page + step, 0), len(self.MANUAL_PAGES) - 1)
                if page != self.manual_page:
                    self.manual_page = page
                    self.audio.play("menu_move")
            return

        if self.game_over:
            if key == pygame.K_r:
                self._reset_run()
            elif key in (pygame.K_RETURN, pygame.K_ESCAPE):
                self.audio.play("menu_cancel")
                self.game_over = False
                self.scene = self.SCENE_TITLE
                self.menu_selection = 0
            return

        if self.victory:
            if key == pygame.K_r:
                self._reset_run()
            elif key in (pygame.K_LEFT, pygame.K_a):
                if self.ending_page > 0:
                    self.ending_page -= 1
                    self.audio.play("menu_move")
            elif key in (pygame.K_RIGHT, pygame.K_d):
                if self.ending_page < len(self.ENDING_PAGES) - 1:
                    self.ending_page += 1
                    self.audio.play("menu_move")
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.ending_page < len(self.ENDING_PAGES) - 1:
                    self.ending_page += 1
                    self.audio.play("menu_ok")
                else:
                    self.audio.play("menu_cancel")
                    self.victory = False
                    self.scene = self.SCENE_TITLE
                    self.menu_selection = 0
            elif key == pygame.K_ESCAPE:
                self.audio.play("menu_cancel")
                self.victory = False
                self.scene = self.SCENE_TITLE
                self.menu_selection = 0
            return

        if key == pygame.K_ESCAPE:
            self.running = False
        elif key == pygame.K_z:
            self.shoot_requested = True
        elif key == pygame.K_F1:
            self.paused = not self.paused
        elif key == pygame.K_F2:
            self.debug_overlay = not self.debug_overlay
        elif key == pygame.K_F3:
            self.god_mode = not self.god_mode
            self.audio.play("menu_ok")

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
    def _shot_offsets(self) -> tuple[float, ...]:
        """按当前火力返回自机弹的横向偏移：单发 / 双发 / 四发。"""
        if self.power >= config.ITEM_POWER_MAX:
            return (-18.0, -6.0, 6.0, 18.0)
        if self.power >= config.PLAYER_POWER_DOUBLE:
            return (-10.0, 10.0)
        return (0.0,)

    def _spawn_player_shots(self, dt: float) -> None:
        """按住射击键时按固定间隔发射玩家弹；弹数随火力提升。"""
        self.fire_timer = max(0.0, self.fire_timer - dt)
        if self.shooting and self.fire_timer <= 0.0:
            muzzle_y = self.player.pos.y - self.player.radius
            for offset in self._shot_offsets():
                self.player_shots.append(
                    PlayerShot(self.player.pos.x + offset, muzzle_y)
                )
            self.audio.play("shot")
            self.fire_timer = config.PLAYER_FIRE_INTERVAL

    def _boss_attack_origin(self) -> Vector2:
        """返回立绘身体处的弹幕发射点，区别于 Boss 立绘的脸部中心。"""
        return self.boss.pos + Vector2(*config.BOSS_ATTACK_ORIGIN_OFFSET)

    def _spawn_boss_attack(self) -> None:
        """按 Boss 阶段发射扇形瞄准弹、环形混合弹幕或旋转螺旋。"""
        art = self.art
        origin = self._boss_attack_origin()
        if self.boss.phase == 1:
            direction = self.player.pos - origin
            if direction.length_squared() == 0:
                direction = Vector2(0.0, 1.0)
            base_angle = math.atan2(direction.y, direction.x)
            middle = (config.BOSS_FAN_COUNT - 1) / 2
            for i in range(config.BOSS_FAN_COUNT):
                offset = (i - middle) * math.radians(config.BOSS_FAN_STEP_DEGREES)
                angle = base_angle + offset
                cyan_side = i % 2 == 1
                self.bullets.append(Bullet(
                    origin.x,
                    origin.y,
                    math.cos(angle) * config.BOSS_ATTACK_SPEED,
                    math.sin(angle) * config.BOSS_ATTACK_SPEED,
                    radius=config.BULLET_SMALL_RADIUS,
                    color=config.CYAN if cyan_side else config.RED,
                    sprite=art.bullet_small["blue" if cyan_side else "red"],
                ))
            return

        if self.boss.phase == 2:
            # 阶段 2：外圈大玉 + 内圈交错的小玉，形成双层环形弹幕
            for i in range(config.BOSS_RING_COUNT):
                angle = math.tau * i / config.BOSS_RING_COUNT
                self.bullets.append(Bullet(
                    origin.x,
                    origin.y,
                    math.cos(angle) * config.BOSS_ATTACK_SPEED,
                    math.sin(angle) * config.BOSS_ATTACK_SPEED,
                    radius=config.BULLET_LARGE_RADIUS,
                    color=config.MAGENTA,
                    sprite=art.bullet_large["magenta"],
                ))

            small_count = config.BOSS_RING_COUNT * 2
            for i in range(small_count):
                angle = math.tau * i / small_count + math.pi / small_count
                speed = config.BOSS_ATTACK_SPEED * 0.72
                self.bullets.append(Bullet(
                    origin.x,
                    origin.y,
                    math.cos(angle) * speed,
                    math.sin(angle) * speed,
                    radius=config.BULLET_SMALL_RADIUS,
                    color=config.WHITE,
                    sprite=art.bullet_small["white"],
                ))
            return

        # 阶段 3：多臂旋转螺旋 + 一圈随机散射
        step = math.tau / config.BOSS_SPIRAL_ARMS
        for i in range(config.BOSS_SPIRAL_ARMS):
            angle = self.spiral_angle + i * step
            self.bullets.append(Bullet(
                origin.x,
                origin.y,
                math.cos(angle) * config.BOSS_ATTACK_SPEED,
                math.sin(angle) * config.BOSS_ATTACK_SPEED,
                radius=config.BULLET_SMALL_RADIUS,
                color=config.PURPLE,
                sprite=art.bullet_small["blue"],
            ))
        self.spiral_angle = (
            self.spiral_angle + math.radians(config.BOSS_SPIRAL_STEP_DEGREES)
        ) % math.tau

        for _ in range(config.BOSS_SCATTER_COUNT):
            angle = random.uniform(0.0, math.tau)
            speed = random.uniform(
                config.BOSS_SCATTER_SPEED_MIN, config.BOSS_SCATTER_SPEED_MAX
            )
            self.bullets.append(Bullet(
                origin.x,
                origin.y,
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                radius=config.BULLET_LARGE_RADIUS,
                color=config.MAGENTA,
                sprite=art.bullet_large["magenta"],
            ))

    def _update_boss_attacks(self, dt: float) -> None:
        """按阶段发射弹幕；符卡限时耗尽则强制推进到下一阶段。"""
        if not self.boss.alive:
            return

        phase = self.boss.phase
        interval = {
            1: config.BOSS_PHASE1_INTERVAL,
            2: config.BOSS_PHASE2_INTERVAL,
        }.get(phase, config.BOSS_PHASE3_INTERVAL)
        if phase != self.boss_attack_phase:
            self.boss_attack_phase = phase
            self.boss_attack_timer = interval
            self.phase_timer = config.BOSS_PHASE_TIME_LIMIT
            if phase > 1:
                self.score += config.PHASE_SCORE
                self.audio.play("phase_change")
                # 每进入新阶段掉落一批火力道具；第三段额外给一个 1UP
                self._spawn_items(
                    self.boss.pos.x, self.boss.pos.y, "power",
                    config.BOSS_PHASE_DROP_POWER,
                )
                if phase == 3:
                    self._spawn_items(
                        self.boss.pos.x, self.boss.pos.y + 44.0, "life", 1
                    )

        self.phase_timer = max(0.0, self.phase_timer - dt)
        if self.phase_timer <= 0.0:
            self._force_phase_end()
            return

        self.boss_attack_timer -= dt
        if self.boss_attack_timer > 0.0:
            return

        self._spawn_boss_attack()
        self.boss_attack_timer = interval

    def _force_phase_end(self) -> None:
        """符卡倒计时归零：把当前阶段直接推到尽头。

        前两段超时即降到本段末尾（进入下一段），最后一段超时视为 Boss 被击破，
        与原作「符卡时间到即结束该符卡」的处理一致。
        """
        segment = self.boss.max_hp / 3.0
        phase = self.boss.phase
        if phase == 1:
            self.boss.hp = min(self.boss.hp, segment * 2.0 - 1.0)
            self.phase_timer = config.BOSS_PHASE_TIME_LIMIT
        elif phase == 2:
            self.boss.hp = min(self.boss.hp, segment - 1.0)
            self.phase_timer = config.BOSS_PHASE_TIME_LIMIT
        else:
            self.boss.hp = 0.0
            self.boss.alive = False

    def _check_boss_collisions(self) -> None:
        """用相对运动线段检测玩家弹与移动 Boss 的碰撞。"""
        if self.boss.alive:
            for shot in self.player_shots:
                if not shot.alive:
                    continue
                self.debug_stats["boss_sweeps"] += 1
                x1 = shot.prev_pos.x - self.boss.prev_pos.x
                y1 = shot.prev_pos.y - self.boss.prev_pos.y
                x2 = shot.pos.x - self.boss.pos.x
                y2 = shot.pos.y - self.boss.pos.y
                if collision.segment_circle(
                        x1, y1, x2, y2, 0.0, 0.0,
                        shot.radius + self.boss.radius):
                    shot.alive = False
                    self.debug_stats["boss_hits"] += 1
                    self.boss.take_damage(shot.damage)
                    self.boss_flash = config.BOSS_FLASH_DURATION
                    self.audio.play("enemy_hit")
                    self.effects.append(Effect(
                        shot.pos.x, shot.pos.y, self.art.hit_spark,
                        config.HIT_SPARK_DURATION, start_scale=0.7,
                        end_scale=1.1,
                    ))
                    if not self.boss.alive:
                        break

        self.player_shots = [shot for shot in self.player_shots if shot.alive]
        if not self.boss.alive:
            self._on_boss_defeated()

    def _check_fairy_collisions(self) -> None:
        """玩家弹与可击破妖精的扫掠判定；击破后按掉落表生成道具。"""
        if not self.fairies:
            return
        for shot in self.player_shots:
            if not shot.alive:
                continue
            for fairy in self.fairies:
                if not fairy.alive:
                    continue
                x1 = shot.prev_pos.x - fairy.prev_pos.x
                y1 = shot.prev_pos.y - fairy.prev_pos.y
                x2 = shot.pos.x - fairy.pos.x
                y2 = shot.pos.y - fairy.pos.y
                if collision.segment_circle(
                        x1, y1, x2, y2, 0.0, 0.0,
                        shot.radius + fairy.radius):
                    shot.alive = False
                    fairy.take_damage(shot.damage)
                    fairy.hit_flash = config.BOSS_FLASH_DURATION
                    self.audio.play("enemy_hit")
                    self.effects.append(Effect(
                        shot.pos.x, shot.pos.y, self.art.hit_spark,
                        config.HIT_SPARK_DURATION, start_scale=0.7,
                        end_scale=1.1,
                    ))
                    if not fairy.alive:
                        self._on_fairy_defeated(fairy)
                    break

        self.player_shots = [shot for shot in self.player_shots if shot.alive]
        self.fairies = [fairy for fairy in self.fairies if fairy.alive]

    def _on_fairy_defeated(self, fairy: Fairy) -> None:
        """击破妖精：轮换掉落 POINT/POWER，并低概率掉落 LIFE。"""
        self.audio.play("enemy_dead")
        self.effects.append(Effect(
            fairy.pos.x, fairy.pos.y, self.art.boss_burst,
            config.BURST_DURATION, start_scale=0.14, end_scale=0.36,
            start_alpha=200, end_alpha=0,
        ))
        self.fairy_kill_count += 1
        if random.random() < config.FAIRY_LIFE_DROP_CHANCE:
            kind = "life"
        else:
            pattern = config.FAIRY_DROP_PATTERN
            kind = pattern[(self.fairy_kill_count - 1) % len(pattern)]
        self._spawn_items(
            fairy.pos.x, fairy.pos.y, kind, config.FAIRY_POINT_DROPS
        )

    def _spawn_items(self, x: float, y: float, kind: str, count: int) -> None:
        """在 (x, y) 附近撒出若干道具，避免彼此完全重叠。"""
        for _ in range(max(0, count)):
            self.items.append(Item(
                x + random.uniform(-36.0, 36.0),
                y + random.uniform(-18.0, 18.0),
                kind,
                sprite=self.art.item_sprites[kind],
            ))

    def _collect_item(self, item: Item) -> None:
        """拾取道具：按种类增加火力 / 分数 / 残机。"""
        item.alive = False
        self.item_total += 1
        if item.kind == "power":
            if self.power >= config.ITEM_POWER_MAX:
                self.score += config.ITEM_POWER_FULL_SCORE
            else:
                self.power = min(
                    config.ITEM_POWER_MAX, self.power + config.ITEM_POWER_GAIN
                )
        elif item.kind == "point":
            self.score += config.ITEM_POINT_SCORE
        elif item.kind == "life":
            self.lives = min(config.PLAYER_LIVES, self.lives + 1)
        self.audio.play("menu_ok")

    def _update_items(self, dt: float) -> None:
        """推进道具：靠近自机时改为磁吸方向，接触后拾取，出屏回收。"""
        for item in self.items:
            if not item.alive:
                continue
            offset = self.player.pos - item.pos
            distance = offset.length()
            if 0.0 < distance <= config.ITEM_MAGNET_RADIUS:
                item.vel = offset * (config.ITEM_MAGNET_SPEED / distance)
            elif distance == 0.0:
                item.vel = Vector2(0.0, 0.0)
            else:
                item.vel = Vector2(0.0, config.ITEM_FALL_SPEED)
            item.update(dt)
            if item.alive and item.pos.distance_to(self.player.pos) <= item.radius:
                self._collect_item(item)
        self.items = [item for item in self.items if item.alive]

    def _on_boss_defeated(self) -> None:
        """击破 Boss：结算分数、播放大爆特效并清空弹幕。"""
        self.score += config.VICTORY_SCORE
        self.audio.play("enemy_dead")
        self._register_hiscore()
        self.effects.append(Effect(
            self.boss.pos.x, self.boss.pos.y, self.art.boss_burst,
            config.BURST_DURATION, start_scale=0.4, end_scale=1.3,
        ))
        self.victory = True
        self.ending_page = 0
        self.bullets.clear()
        self.player_shots.clear()

    def _register_hiscore(self) -> None:
        """刷新并持久化最高分（无写权限时静默忽略）。"""
        if self.score > self.hiscore:
            self.hiscore = self.score
            _save_hiscore(self.hiscore)

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
        self.score = 0                 # 单局分数重置，最高分保留
        self.power = config.PLAYER_POWER_START
        self.item_total = 0
        self.spiral_angle = 0.0
        self.effects.clear()
        self.items.clear()
        self.fairies.clear()
        self.fairy_kill_count = 0
        self.fairy_timer = config.FAIRY_SPAWN_MIN
        self.phase_timer = config.BOSS_PHASE_TIME_LIMIT
        self.boss_flash = 0.0
        self.graze_fx_cooldown = 0.0
        self.lives = config.PLAYER_LIVES
        self.invulnerable_timer = 0.0
        self.focus = False
        self.paused = False
        self.victory = False
        self.ending_page = 0
        self.game_over = False
        self.entry_card_timer = self.ENTRY_CARD_DURATION
        self.scene = self.SCENE_PLAYING
        self.animation_timer = 0.0
        self.audio.play("alert")

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
        self.debug_stats["candidates"] = len(candidates)
        p0x, p0y = self.player.prev_pos.x, self.player.prev_pos.y
        for b in candidates:
            if not b.alive or self.invulnerable_timer > 0.0:
                continue
            self.debug_stats["sweeps"] += 1

            # 转为相对运动：子弹上一帧相对玩家上一帧，至本帧相对位置。
            x1, y1 = b.prev_pos.x - p0x, b.prev_pos.y - p0y
            x2, y2 = b.pos.x - px, b.pos.y - py

            # 先判内层命中区，命中后直接跳过擦弹判定
            if collision.segment_circle(x1, y1, x2, y2, 0.0, 0.0,
                                        self.player.radius + b.radius):
                if not getattr(self, "god_mode", False):
                    self.debug_stats["hits"] += 1
                    self._on_player_hit(b)
                continue

            # 未命中，再判外层擦弹区（每颗子弹只计一次）
            if not b.grazed and collision.segment_circle(
                    x1, y1, x2, y2, 0.0, 0.0,
                    self.player.graze_radius + b.radius):
                b.grazed = True
                self.debug_stats["grazes"] += 1
                self.player.graze_count += 1
                self.graze_total += 1
                self.score += config.GRAZE_SCORE
                # 擦弹星环按冷却节流，避免密集弹幕下特效刷屏
                if self.graze_fx_cooldown <= 0.0:
                    self.effects.append(Effect(
                        self.player.pos.x, self.player.pos.y,
                        self.art.graze_ring, config.GRAZE_RING_DURATION,
                        start_scale=0.6, end_scale=1.5,
                    ))
                    self.audio.play("graze")
                    self.graze_fx_cooldown = 0.06

    def _on_player_hit(self, bullet: Bullet) -> None:
        if (
            self.invulnerable_timer > 0.0
            or self.game_over
            or getattr(self, "god_mode", False)
        ):
            return

        bullet.alive = False
        self.hit_total += 1
        self.hit_flash = 0.25
        self.audio.play("player_dead")
        self.lives -= 1
        self.bullets.clear()
        self.effects.append(Effect(
            self.player.pos.x, self.player.pos.y, self.art.boss_burst,
            config.BURST_DURATION, start_scale=0.22, end_scale=0.65,
            start_alpha=190, end_alpha=0,
        ))
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

    def _advance_effects(self, dt: float) -> None:
        """推进所有一次性特效，并回收播完的实例。"""
        for effect in self.effects:
            effect.update(dt)
        self.effects = [effect for effect in self.effects if effect.alive]

    def _update_fairies(self, dt: float) -> None:
        """定时生成可击破妖精，混用原作两组妖精动画。"""
        self.fairy_timer -= dt
        if self.fairy_timer <= 0.0:
            self.fairy_timer = random.uniform(
                config.FAIRY_SPAWN_MIN, config.FAIRY_SPAWN_MAX
            )
            self.fairies.append(Fairy(
                random.uniform(config.PLAYFIELD_LEFT + 80,
                               config.PLAYFIELD_RIGHT - 80),
                config.PLAYFIELD_TOP - 30.0,
                random.uniform(config.FAIRY_SPEED_MIN, config.FAIRY_SPEED_MAX),
                random.uniform(config.FAIRY_SWAY_MIN, config.FAIRY_SWAY_MAX),
                variant=random.random() < config.FAIRY_VARIANT_CHANCE,
            ))
        for fairy in self.fairies:
            fairy.update(dt)
        self.fairies = [fairy for fairy in self.fairies if fairy.alive]

    def _update_music(self) -> None:
        """按当前场景切换循环背景音乐；同一首不会被打断重来。"""
        if self.scene in (self.SCENE_TITLE, self.SCENE_CONTROLS):
            self.audio.play_music("title")
        elif self.scene == self.SCENE_PLAYING:
            if self.victory:
                self.audio.play_music("ending")
            elif self.game_over:
                self.audio.play_music("boss" if self.boss.phase >= 3 else "stage")
            else:
                # 最终符卡换成 Boss 曲，前两段用关卡曲
                self.audio.play_music("boss" if self.boss.phase >= 3 else "stage")

    def update(self, dt: float) -> None:
        self._update_music()
        if self.scene != self.SCENE_PLAYING:
            return
        if self.paused:
            self.shoot_requested = False
            return
        if self.victory or self.game_over:
            # 结算画面仍需让特效播完、红屏闪烁淡出
            self.shoot_requested = False
            self._advance_effects(dt)
            self.hit_flash = max(0.0, self.hit_flash - dt)
            return
        if getattr(self, "entry_card_timer", 0.0) > 0.0:
            self.entry_card_timer = max(0.0, self.entry_card_timer - dt)
            self.shoot_requested = False
            return

        self._advance_effects(dt)
        self.invulnerable_timer = max(0.0, self.invulnerable_timer - dt)
        self.boss_flash = max(0.0, self.boss_flash - dt)
        self.graze_fx_cooldown = max(0.0, self.graze_fx_cooldown - dt)
        self.debug_stats = self._empty_debug_stats()
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
        self._update_fairies(dt)
        self._update_items(dt)

        if self.boss.alive:
            self.boss.update(dt)
        self._spawn_player_shots(dt)
        self.shoot_requested = False
        for shot in self.player_shots:
            shot.update(dt)
        self._check_fairy_collisions()
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
            self._draw_manual_screen()
            return

        field_origin = (config.PLAYFIELD_LEFT, config.PLAYFIELD_TOP)
        self.screen.blit(self.art.scene_background, (0, 0))
        self.screen.blit(self.art.playfield_background, field_origin)
        self.screen.blit(self.playfield_shade, field_origin)
        self.screen.blit(self.field_vignette, field_origin)

        for fairy in self.fairies:
            fairy.draw(
                self.screen,
                (
                    self.art.fairy_variant_frames
                    if fairy.variant else self.art.fairy_frames
                ),
                flash=fairy.hit_flash / config.BOSS_FLASH_DURATION,
            )

        for item in self.items:
            item.draw(self.screen, self.art.item_halo)

        boss_sprite = self.art.boss_faces[
            min(self.boss.phase, len(self.art.boss_faces)) - 1
        ]
        if self.boss_flash > 0.0 and self.boss.alive:
            boss_sprite = _flash_sprite(
                boss_sprite, self.boss_flash / config.BOSS_FLASH_DURATION
            )
        self.boss.draw(self.screen, boss_sprite)

        for shot in self.player_shots:
            if shot.alive:
                shot.draw(self.screen, self.art.player_shot)
        blinking = (
            self.invulnerable_timer > 0.0
            and int(self.invulnerable_timer * 12) % 2 == 0
        )
        if not blinking:
            # 按本帧横向移动方向挑帧组，静止时回到直立组
            if self.player.vel.x < -1.0:
                frames = self.art.player_frames_left
            elif self.player.vel.x > 1.0:
                frames = self.art.player_frames_right
            else:
                frames = self.art.player_frames
            self.player.draw(
                self.screen,
                focus=self.focus,
                sprite=frames[int(self.animation_timer * 8) % len(frames)],
            )

        for b in self.bullets:
            b.draw(self.screen)          # 子弹自持贴图，无需外部查表
        for effect in self.effects:
            effect.draw(self.screen)

        if self.hit_flash > 0:
            self.hit_overlay.set_alpha(round(90 * self.hit_flash / 0.25))
            self.screen.blit(self.hit_overlay, field_origin)

        if self.debug_overlay:
            self._draw_debug_overlay()

        self._draw_phase_hud()
        self._draw_hud()

        if self.paused:
            self._draw_pause_card()
        elif self.game_over:
            self._draw_ending(self.art.ending_defeat, victory=False)
        elif self.victory:
            ending_background = (
                self.art.ending_victory,
                self.art.ending_afterword,
                self.art.ending_credits,
            )[self.ending_page]
            self._draw_ending(ending_background, victory=True)
        elif getattr(self, "entry_card_timer", 0.0) > 0.0:
            self._draw_entry_card()

    def _draw_ornate_panel(self, rect: pygame.Rect) -> None:
        """绘制半透明双线描金卡片，底图始终保留原作素材。"""
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((10, 5, 12, 236))
        self.screen.blit(panel, rect.topleft)
        pygame.draw.rect(self.screen, config.GOLD, rect, 2)
        pygame.draw.rect(self.screen, (120, 68, 54), rect.inflate(-14, -14), 1)

    def _draw_entry_card(self) -> None:
        """开战过场：以原作场景与 Boss 立绘呈现异变和首张符卡。"""
        progress = min(1.0, self.entry_card_timer / self.ENTRY_CARD_DURATION)
        self.entry_shade.set_alpha(round(255 * progress))
        self.screen.blit(self.entry_shade, (0, 0))

        panel = pygame.Rect(158, 244, 964, 472)
        self._draw_ornate_panel(panel)
        left = panel.left + 48
        self.screen.blit(
            self.font.render("異変調査記録  /  INCIDENT FILE 01", True, config.MUTED),
            (left, panel.top + 38),
        )
        self.screen.blit(
            self.font_big.render("紅霧異変", True, config.PALE_GOLD),
            (left, panel.top + 88),
        )
        self.screen.blit(
            self.font.render("～ Scarlet Mist Incident ～", True, config.WHITE),
            (left, panel.top + 148),
        )
        pygame.draw.line(
            self.screen, config.GOLD,
            (left, panel.top + 198), (panel.right - 48, panel.top + 198), 1,
        )
        self.screen.blit(
            self.font.render("舞台  /  湖畔・紅魔館", True, config.PALE_GOLD),
            (left, panel.top + 222),
        )
        self.screen.blit(
            self.font.render("首領  /  蕾米莉亞·史卡雷特", True, config.WHITE),
            (left, panel.top + 266),
        )
        self.screen.blit(
            self.font.render("第一符卡  「紅符 · 猩紅射擊」", True, config.WHITE),
            (left, panel.top + 310),
        )
        self.screen.blit(
            self.art.boss_faces[0],
            self.art.boss_faces[0].get_rect(
                midright=(panel.right - 54, panel.centery + 8)
            ),
        )
        self.screen.blit(
            self.font.render("避開彈幕，破除符卡。", True, config.PALE_GOLD),
            (left, panel.bottom - 62),
        )

    def _draw_ending(self, background: pygame.Surface, victory: bool) -> None:
        """結算回顾：原作插图、符卡结果、战绩与再战指引。"""
        self.screen.blit(background, (0, 0))
        self.screen.blit(self.ending_shade, (0, 0))
        panel = pygame.Rect(120, 128, 1040, 704)
        self._draw_ornate_panel(panel)
        left = panel.left + 58
        phase = min(max(self.boss.phase, 1), len(config.BOSS_PHASE_NAMES))
        spell_name = config.BOSS_PHASE_NAMES[phase - 1]
        if victory and self.ending_page > 0:
            self._draw_victory_text_page(panel)
            return

        heading = "異変解決" if victory else "霊力尽きる"
        english = "INCIDENT RESOLVED" if victory else "INCIDENT UNRESOLVED"
        self.screen.blit(
            self.font_big.render(heading, True, config.PALE_GOLD),
            (left, panel.top + 48),
        )
        self.screen.blit(
            self.font.render(english, True, config.MUTED),
            (left, panel.top + 112),
        )
        pygame.draw.line(
            self.screen, config.GOLD,
            (left, panel.top + 158), (panel.right - 58, panel.top + 158), 1,
        )
        self.screen.blit(
            self.font.render("紅霧異変  /  紅魔館異聞", True, config.PALE_GOLD),
            (left, panel.top + 184),
        )
        self.screen.blit(
            self.font.render(
                "三重符卡  /  SPELL CARD CLEAR  3 / 3"
                if victory else f"到達符卡  /  {phase} / 3  {spell_name}",
                True, config.WHITE,
            ),
            (left, panel.top + 232),
        )
        self.screen.blit(
            self.font.render(
                f"得分  {self.score:08d}      最高分  {self.hiscore:08d}",
                True, config.WHITE,
            ),
            (left, panel.top + 302),
        )
        self.screen.blit(
            self.font.render(
                f"擦彈 {self.graze_total}    命中 {self.hit_total}    "
                f"道具 {self.item_total}",
                True, config.MUTED,
            ),
            (left, panel.top + 350),
        )

        result_rect = self.art.result_screen.get_rect(
            midright=(panel.right - 58, panel.top + 380)
        )
        pygame.draw.rect(
            self.screen, config.GOLD, result_rect.inflate(4, 4), 1
        )
        self.screen.blit(
            self.art.result_screen, result_rect,
        )
        self.screen.blit(
            self.font.render("紅魔郷 SCORE / RESULT", True, config.PALE_GOLD),
            (result_rect.left, result_rect.bottom + 16),
        )
        pygame.draw.line(
            self.screen, (120, 68, 54),
            (left, panel.bottom - 116), (panel.right - 58, panel.bottom - 116), 1,
        )
        self.screen.blit(
            self.font.render(
                "Enter / → 閱讀後記  ·  R 再戰  ·  Esc 返回標題",
                True, config.WHITE,
            ),
            (left, panel.bottom - 80),
        )

    def _draw_victory_text_page(self, panel: pygame.Rect) -> None:
        """原作式後記與鳴謝頁：沿用金邊卡片，襯以對應結局原圖。"""
        page = self.ending_page
        left = panel.left + 58
        right = panel.right - 58
        if page == 1:
            title = "後記"
            subtitle = "AFTERWORD  /  異変のあと"
        else:
            title = "謝辞"
            subtitle = "STAFF ROLL  /  ACKNOWLEDGMENTS"

        self.screen.blit(
            self.font_big.render(title, True, config.PALE_GOLD),
            (left, panel.top + 42),
        )
        self.screen.blit(
            self.font.render(subtitle, True, config.MUTED),
            (left, panel.top + 108),
        )
        page_label = self.font.render(
            f"{page + 1} / {len(self.ENDING_PAGES)}", True, config.PALE_GOLD
        )
        self.screen.blit(page_label, page_label.get_rect(topright=(right, panel.top + 68)))
        pygame.draw.line(
            self.screen, config.GOLD,
            (left, panel.top + 158), (right, panel.top + 158), 1,
        )

        if page == 1:
            y = panel.top + 194
            for line in self.VICTORY_AFTERWORD:
                if line:
                    self.screen.blit(
                        self.font.render(line, True, config.WHITE), (left, y)
                    )
                    y += 38
                else:
                    y += 22
            hint = "← 戰績  ·  → / Enter 謝辞  ·  R 再戰  ·  Esc 標題"
        else:
            y = panel.top + 198
            for label, value in self.VICTORY_CREDITS:
                self.screen.blit(
                    self.font.render(label, True, config.PALE_GOLD), (left, y)
                )
                self.screen.blit(
                    self.font.render(value, True, config.WHITE),
                    (left + 190, y),
                )
                y += 48
            for index, line in enumerate(self.VICTORY_THANKS):
                self._draw_center_text(
                    line, config.PALE_GOLD, font=self.font,
                    y=panel.bottom - 190 + index * 42,
                    center_x=panel.centerx,
                )
            hint = "← 後記  ·  Enter / Esc 返回標題  ·  R 再戰"

        divider_y = panel.bottom - 116
        pygame.draw.line(
            self.screen, (120, 68, 54),
            (left, divider_y), (right, divider_y), 1,
        )
        self.screen.blit(
            self.font.render(hint, True, config.WHITE),
            (left, panel.bottom - 80),
        )

    def _draw_pause_card(self) -> None:
        """暂停过场：保留战场和 HUD，展示正在展开的符卡。"""
        panel = pygame.Rect(198, 304, 884, 352)
        self._draw_ornate_panel(panel)
        center_x = panel.centerx
        self._draw_center_text(
            "弾幕一時停止", config.PALE_GOLD,
            y=panel.top + 62, center_x=center_x,
        )
        self._draw_center_text(
            "PAUSED  /  SPELL CARD", config.MUTED,
            font=self.font, y=panel.top + 124, center_x=center_x,
        )
        phase = min(max(self.boss.phase, 1), len(config.BOSS_PHASE_NAMES))
        self._draw_center_text(
            f"第 {phase} 符卡  「{config.BOSS_PHASE_NAMES[phase - 1]}」",
            config.WHITE, font=self.font, y=panel.top + 192, center_x=center_x,
        )
        self._draw_center_text(
            "F1 继续弹幕  ·  Esc 退出异变调查",
            config.PALE_GOLD, font=self.font,
            y=panel.top + 258, center_x=center_x,
        )

    def _draw_title_screen(self) -> None:
        self.screen.blit(self.title_background, (0, 0))
        self.screen.blit(self.title_shade, (0, 0))
        title_panel = pygame.Rect(*self.TITLE_INFO_PANEL_RECT)
        self._draw_ornate_panel(title_panel)
        left = title_panel.left + 28
        self.screen.blit(
            self.font.render("幻想郷異変録  /  STORY 01", True, config.MUTED),
            (left, title_panel.top + 28),
        )
        self.screen.blit(
            self.font_big.render("紅霧異変", True, config.PALE_GOLD),
            (left, title_panel.top + 76),
        )
        self.screen.blit(
            self.font.render("～ Scarlet Mist Incident ～", True, config.WHITE),
            (left, title_panel.top + 132),
        )
        pygame.draw.line(
            self.screen, config.GOLD,
            (left, title_panel.top + 176),
            (title_panel.right - 28, title_panel.top + 176), 1,
        )
        self.screen.blit(
            self.font.render(
                "幻想乡被紅霧籠罩，",
                True, config.WHITE,
            ),
            (left, title_panel.top + 196),
        )
        self.screen.blit(
            self.font.render(
                "異變的源頭指向湖畔洋館。",
                True, config.WHITE,
            ),
            (left, title_panel.top + 230),
        )
        self.screen.blit(
            self.font.render(
                "穿越三重符卡，尋回夜色。",
                True, config.PALE_GOLD,
            ),
            (left, title_panel.top + 274),
        )
        self.screen.blit(
            self.font.render("異変退治  /  DANMAKU", True, config.MUTED),
            (left, title_panel.top + 316),
        )
        self.screen.blit(
            self.font.render("↑ / ↓ 選擇    Enter 開始", True, config.WHITE),
            (800, 425),
        )

        for index, (selected_image, idle_image) in enumerate(self.title_menu_images):
            image = selected_image if index == self.menu_selection else idle_image
            self.screen.blit(image, (800, 500 + index * 112))

    def _draw_manual_screen(self) -> None:
        """说明书：哥特风双线描金边框 + 页签，依次为背景、用语、操作。"""
        self.screen.blit(self.title_background, (0, 0))
        self.screen.blit(self.title_shade, (0, 0))

        frame = pygame.Rect(56, 56, config.SCREEN_W - 112, config.SCREEN_H - 112)
        pygame.draw.rect(self.screen, config.GOLD, frame, 2)
        pygame.draw.rect(self.screen, (120, 68, 54), frame.inflate(-16, -16), 1)
        inner_left = frame.left + 44
        inner_right = frame.right - 44

        subtitle = ("被染红的夏夜，与三重符卡",
                    "幻想乡用语与玩法解说",
                    "键位分配一览")[self.manual_page]
        heading = "幻想乡异闻 ～ Scarlet Danmaku"
        self.screen.blit(self.font_big.render(heading, True, config.PALE_GOLD),
                         (inner_left, frame.top + 34))
        self.screen.blit(self.font.render(subtitle, True, config.MUTED),
                         (inner_left, frame.top + 92))
        pygame.draw.line(
            self.screen, config.GOLD,
            (inner_left, frame.top + 132), (inner_right, frame.top + 132), 1,
        )

        # 右上角页签，当前页用绯红底、未选中页压暗
        tab_width = 150
        for index, label in enumerate(self.MANUAL_PAGES):
            tab = pygame.Rect(
                inner_right - (len(self.MANUAL_PAGES) - index) * tab_width,
                frame.top + 40, tab_width - 8, 40,
            )
            active = index == self.manual_page
            pygame.draw.rect(
                self.screen, (92, 20, 34) if active else (34, 14, 22), tab
            )
            pygame.draw.rect(self.screen, config.GOLD, tab, 1)
            text = f"{'一二三'[index]}、{label}"
            surface = self.font.render(
                text, True, config.PALE_GOLD if active else config.MUTED
            )
            self.screen.blit(surface, surface.get_rect(center=tab.center))

        if self.manual_page == 0:
            self._draw_story_page(inner_left, frame.top + 166)
        elif self.manual_page == 1:
            self._draw_terms_page(inner_left, inner_right, frame.top + 166)
        else:
            self._draw_controls_page(inner_left, inner_right, frame.top + 166)

        hint = self.font.render(
            "← → 翻阅说明页        Enter / Esc 返回标题", True, config.WHITE
        )
        self.screen.blit(hint, (inner_left, frame.bottom - 56))

    def _draw_story_page(self, left: int, top: int) -> None:
        """背景说明正文：段落之间自动留白。"""
        y = top
        for line in self.MANUAL_STORY:
            if line:
                self.screen.blit(self.font.render(line, True, config.WHITE),
                                 (left, y))
            y += 42

    def _draw_terms_page(self, left: int, right: int, top: int) -> None:
        """用语解说：左列术语、右列释义。"""
        for index, (term, meaning) in enumerate(self.MANUAL_TERMS):
            y = top + index * 42
            self.screen.blit(self.font.render(term, True, config.PALE_GOLD),
                             (left, y))
            self.screen.blit(self.font.render(meaning, True, config.WHITE),
                             (left + 280, y))

    def _draw_controls_page(self, left: int, right: int, top: int) -> None:
        """操作指南：左侧键位、右侧动作。"""
        for index, (key, action) in enumerate(self.MANUAL_KEYS):
            y = top + index * 42
            self.screen.blit(self.font.render(key, True, config.PALE_GOLD),
                             (left, y))
            self.screen.blit(self.font.render(action, True, config.WHITE),
                             (left + 250, y))

        y = top + len(self.MANUAL_KEYS) * 42 + 24
        pygame.draw.line(self.screen, (120, 68, 54), (left, y), (right, y), 1)
        note = self.font.render(
            "符卡、道具与判定点的含义，见「二、用语解说」。", True, config.MUTED
        )
        self.screen.blit(note, (left, y + 24))

    def _draw_text_centered(
            self, text: str, y: int, color, font: pygame.font.Font) -> None:
        surface = font.render(text, True, color)
        center_x = config.PLAYFIELD_LEFT + config.PLAYFIELD_WIDTH // 2
        rect = surface.get_rect(center=(center_x, y))
        self.screen.blit(surface, rect)

    def _draw_debug_overlay(self) -> None:
        """绘制碰撞调试层：空间网格、双层判定圆、扫掠线段与擦弹高亮。

        只读取实体状态，不修改位置或半径，因此开启调试不影响玩法结果。
        """
        field = pygame.Rect(
            config.PLAYFIELD_LEFT,
            config.PLAYFIELD_TOP,
            config.PLAYFIELD_WIDTH,
            config.PLAYFIELD_HEIGHT,
        )

        # 空间网格：与 SpatialGrid 使用的世界坐标对齐（格子以原点为基准）
        grid = pygame.Surface(field.size, pygame.SRCALPHA)
        grid_color = (*config.DEBUG_GRID_COLOR, config.DEBUG_GRID_ALPHA)
        cell = config.GRID_CELL_SIZE
        x = cell - (config.PLAYFIELD_LEFT % cell)
        while x < field.width:
            pygame.draw.line(grid, grid_color, (x, 0), (x, field.height), 1)
            x += cell
        y = cell - (config.PLAYFIELD_TOP % cell)
        while y < field.height:
            pygame.draw.line(grid, grid_color, (0, y), (field.width, y), 1)
            y += cell
        self.screen.blit(grid, field.topleft)

        # 敌弹本帧扫掠线段；已擦弹的子弹加一圈外环
        for b in self.bullets:
            pygame.draw.line(
                self.screen, config.DEBUG_SWEEP_COLOR,
                (round(b.prev_pos.x), round(b.prev_pos.y)),
                (round(b.pos.x), round(b.pos.y)), 1,
            )
            if b.grazed:
                pygame.draw.circle(
                    self.screen, config.DEBUG_GRAZE_COLOR,
                    (round(b.pos.x), round(b.pos.y)), round(b.radius) + 5, 1,
                )

        # Boss 命中区
        if self.boss.alive:
            pygame.draw.circle(
                self.screen, config.DEBUG_HIT_COLOR,
                (round(self.boss.pos.x), round(self.boss.pos.y)),
                round(self.boss.radius), 1,
            )

        # 玩家双层判定：外圈擦弹区、内圈命中区
        center = (round(self.player.pos.x), round(self.player.pos.y))
        pygame.draw.circle(
            self.screen, config.DEBUG_GRAZE_COLOR, center,
            round(self.player.graze_radius), 1,
        )
        pygame.draw.circle(
            self.screen, config.DEBUG_HIT_COLOR, center,
            max(1, round(self.player.radius)), 0,
        )

    def _draw_phase_hud(self) -> None:
        """弹幕场顶部的符卡条：符卡名、剩余段数与倒计时。"""
        bar = pygame.Rect(config.PLAYFIELD_LEFT, config.PLAYFIELD_TOP,
                          config.PLAYFIELD_WIDTH, 40)
        shade = pygame.Surface(bar.size, pygame.SRCALPHA)
        shade.fill((7, 3, 9, 160))
        self.screen.blit(shade, bar.topleft)
        pygame.draw.line(
            self.screen, config.GOLD, bar.bottomleft, bar.bottomright, 1
        )

        total = len(config.BOSS_PHASE_NAMES)
        phase = min(self.boss.phase, total)
        name = config.BOSS_PHASE_NAMES[phase - 1]
        self.screen.blit(
            self.font.render(name, True, config.PALE_GOLD),
            (bar.left + 16, bar.top + 7),
        )

        # 剩余段数：已过的段位画成空心，未过的画成实心
        remaining = total - phase + 1
        marker_x = bar.left + 380
        for index in range(total):
            center = (marker_x + index * 26, bar.centery)
            if index < remaining:
                pygame.draw.circle(self.screen, config.RED, center, 7)
                pygame.draw.circle(self.screen, config.PALE_GOLD, center, 7, 1)
            else:
                pygame.draw.circle(self.screen, config.GRAY, center, 7, 1)

        seconds = max(0.0, self.phase_timer)
        timer = self.font.render(f"{seconds:05.2f}", True, config.WHITE)
        self.screen.blit(timer, timer.get_rect(midright=(bar.right - 16, bar.centery)))

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
            (left, panel.top + 24),
        )
        self.screen.blit(
            self.font.render("SCARLET DEVIL MANOR", True, config.MUTED),
            (left + 2, panel.top + 78),
        )
        pygame.draw.line(
            self.screen, config.GOLD,
            (left, panel.top + 120), (right, panel.top + 120), 1,
        )

        # 计分区：最高分与当前得分，均右对齐
        for index, (label, value) in enumerate((
            ("HISCORE", self.hiscore), ("SCORE", self.score),
        )):
            y = panel.top + 134 + index * 34
            self.screen.blit(self.font.render(label, True, config.MUTED), (left, y))
            value_surface = self.font.render(str(value), True, config.WHITE)
            self.screen.blit(value_surface, value_surface.get_rect(topright=(right, y)))
        pygame.draw.line(
            self.screen, config.GOLD,
            (left, panel.top + 206), (right, panel.top + 206), 1,
        )

        total = len(config.BOSS_PHASE_NAMES)
        self.screen.blit(
            self.font.render("BOSS  /  PHASE", True, config.PALE_GOLD),
            (left, panel.top + 218),
        )
        phase_text = self.font.render(
            f"{min(self.boss.phase, total)} / {total}", True, config.WHITE
        )
        self.screen.blit(phase_text, phase_text.get_rect(topright=(right, panel.top + 218)))
        self.screen.blit(
            self.art.boss_faces[min(self.boss.phase, len(self.art.boss_faces)) - 1],
            (right - self.art.boss_portrait.get_width(), panel.top + 250),
        )

        health_ratio = max(0.0, self.boss.hp / self.boss.max_hp)
        self.screen.blit(
            self.font.render("生命值  /  HP", True, config.MUTED),
            (left, panel.top + 434),
        )
        health_bar = pygame.Rect(left, panel.top + 460, panel.width - 48, 18)
        pygame.draw.rect(self.screen, (47, 19, 28), health_bar)
        fill = health_bar.inflate(-4, -4)
        fill.width = round(fill.width * health_ratio)
        if fill.width > 0:
            pygame.draw.rect(self.screen, config.RED, fill)
        pygame.draw.rect(self.screen, config.GOLD, health_bar, 1)
        pygame.draw.line(
            self.screen, config.GOLD,
            (left, panel.top + 504), (right, panel.top + 504), 1,
        )

        self.screen.blit(
            self.font.render("残机  /  LIVES", True, config.PALE_GOLD),
            (left, panel.top + 516),
        )
        icon_y = panel.top + 506
        icon_x = right - 94
        for index in range(config.PLAYER_LIVES):
            icon = self.art.player_icon.copy()
            icon.set_alpha(255 if index < self.lives else 60)
            self.screen.blit(icon, (icon_x + index * 30, icon_y))
        pygame.draw.line(
            self.screen, config.GOLD,
            (left, panel.top + 560), (right, panel.top + 560), 1,
        )

        rows = (
            ("擦弹  /  GRAZE", self.graze_total),
            ("敌弹  /  BULLETS", len(self.bullets)),
            ("命中  /  HITS", self.hit_total),
        )
        for index, (label, value) in enumerate(rows):
            y = panel.top + 562 + index * 32
            self.screen.blit(self.font.render(label, True, config.MUTED), (left, y))
            value_surface = self.font.render(str(value), True, config.WHITE)
            self.screen.blit(value_surface, value_surface.get_rect(topright=(right, y)))

        # 火力：左侧标签、右侧数值，中间一根本色进度条
        power_y = panel.top + 658
        self.screen.blit(
            self.font.render("火力  /  POWER", True, config.MUTED),
            (left, power_y),
        )
        power_value = self.font.render(f"{self.power:.2f}", True, config.WHITE)
        self.screen.blit(
            power_value, power_value.get_rect(topright=(right, power_y))
        )
        power_bar = pygame.Rect(left + 150, power_y + 9, 110, 12)
        pygame.draw.rect(self.screen, (47, 19, 28), power_bar)
        power_fill = power_bar.inflate(-4, -4)
        power_fill.width = round(
            power_fill.width * min(1.0, self.power / config.ITEM_POWER_MAX)
        )
        if power_fill.width > 0:
            pygame.draw.rect(self.screen, config.GOLD, power_fill)
        pygame.draw.rect(self.screen, config.GOLD, power_bar, 1)

        item_y = panel.top + 690
        self.screen.blit(
            self.font.render("道具  /  ITEM", True, config.MUTED), (left, item_y)
        )
        item_value = self.font.render(str(self.item_total), True, config.WHITE)
        self.screen.blit(item_value, item_value.get_rect(topright=(right, item_y)))

        divider_y = panel.top + 736
        pygame.draw.line(
            self.screen, config.GOLD,
            (left, divider_y), (right, divider_y), 1,
        )
        self.screen.blit(
            self.font.render(
                "调  试  /  DEBUG" if self.debug_overlay else "操  作  /  CONTROL",
                True, config.PALE_GOLD,
            ),
            (left, divider_y + 20),
        )
        if self.god_mode:
            badge = pygame.Rect(right - 104, divider_y + 18, 104, 30)
            pygame.draw.rect(self.screen, (92, 20, 34), badge)
            pygame.draw.rect(self.screen, config.GOLD, badge, 1)
            status = self.font.render("GOD ON", True, config.PALE_GOLD)
            self.screen.blit(status, status.get_rect(center=badge.center))
        if self.debug_overlay:
            stats = self.debug_stats
            debug_rows = (
                ("候选 / CAND", stats["candidates"]),
                ("扫掠 / SWEPT", stats["sweeps"]),
                ("Boss 命中 / HIT", stats["boss_hits"]),
            )
            for index, (label, value) in enumerate(debug_rows):
                y = divider_y + 60 + index * 36
                self.screen.blit(
                    self.font.render(label, True, config.MUTED), (left, y)
                )
                value_surface = self.font.render(str(value), True, config.WHITE)
                self.screen.blit(
                    value_surface, value_surface.get_rect(topright=(right, y))
                )
            return

        hints = (
            "方向键 / WASD   移动",
            "Shift 低速   F3 无敌",
            "Z 射击   F1 暂停   F2 调试",
        )
        for index, hint in enumerate(hints):
            self.screen.blit(
                self.font.render(hint, True, config.WHITE),
                (left, divider_y + 60 + index * 36),
            )

    def _draw_center_text(
            self, text: str, color, font: pygame.font.Font | None = None,
            y: int | None = None, center_x: int | None = None) -> None:
        font = font or self.font_big
        surf = font.render(text, True, color)
        center = (
            center_x if center_x is not None
            else config.PLAYFIELD_LEFT + config.PLAYFIELD_WIDTH // 2,
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
