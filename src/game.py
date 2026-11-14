"""游戏主循环与场景逻辑。

采用「夹紧的时间步长」推进逻辑：每帧用 ``clock.tick`` 得到真实 elapsed，
并夹紧到 ``MAX_DT``，保证物理与碰撞在不同机器上表现一致，同时避免卡顿后穿模。

关卡流程交给 :class:`~src.director.StageDirector`：它按剧本依次给出过场、对话、
杂兵波次与 Boss 战，本类只负责把返回的杂兵投放进场、按需生成 Boss、在 Boss
被击破时回报，并把当前状态画出来。
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pygame
from pygame.math import Vector2

from . import config, collision, spells
from .art import GameArt
from .audio import Audio
from .director import BANNER, FIGHT, TALK, StageDirector
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


def _progress_path() -> Path:
    return Path(__file__).resolve().parent.parent / config.PROGRESS_FILE


def _load_progress() -> dict:
    """读取关卡解锁进度。返回 ``{"unlocked": 1, "all_cleared": false}``。"""
    try:
        data = json.loads(_progress_path().read_text(encoding="utf-8"))
        return {
            "unlocked": int(data.get("unlocked", 1)),
            "all_cleared": bool(data.get("all_cleared", False)),
        }
    except (OSError, ValueError, json.JSONDecodeError):
        return {"unlocked": 1, "all_cleared": False}


def _save_progress(unlocked: int, all_cleared: bool) -> None:
    try:
        _progress_path().write_text(
            json.dumps({"unlocked": unlocked, "all_cleared": all_cleared},
                       ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


class Game:
    """游戏主体：窗口、主循环、输入、碰撞与渲染。"""

    SCENE_TITLE = "title"
    SCENE_CONTROLS = "controls"
    SCENE_STAGE_SELECT = "stage_select"
    SCENE_PLAYING = "playing"
    SCENE_AFTERWORD = "afterword"
    SCENE_CG_GALLERY = "cg_gallery"
    CHEAT_PASSWORD = "472977"          # 作弊模式解锁密码
    ENDING_PAGES = ("result", "afterword", "afterword", "afterword", "credits")
    STAGE_TITLES = ("紅霧の麓", "霧の湖", "紅魔館")
    STAGE_SUBTITLES = (
        "Scarlet Mist  /  Stage 1",
        "Misty Lake  /  Stage 2",
        "Scarlet Devil Mansion  /  Final Stage",
    )
    STAGE_BOSS_NAMES = ("露米婭", "琪露諾", "蕾米莉亞")
    TITLE_INFO_PANEL_RECT = (52, 52, 500, 360)
    MENU_ITEMS = ("开始游戏", "紅霧人物録", "操作说明", "退出游戏")
    MENU_ITEMS_CLEARED = ("开始游戏", "紅霧人物録", "操作说明", "退出游戏", "日后谈")
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
        "　　博丽的巫女循着雾的源头一路追去，行程分成三站。",
        "　先是红雾笼罩的人里近郊，接着是雾气最浓的雾之湖，",
        "　最后是矗立湖畔、掀起整场异变的红魔馆。",
        "",
        "　　每一站都是一场杂兵波次、一位中 Boss、一位关底 Boss。",
        "　躲开绯红的弹雨，逐张符卡破开，",
        "　把这位任性的吸血鬼，从漫长的夜里唤醒吧。",
    )

    # 页面二：世界观与玩法术语
    MANUAL_TERMS = (
        ("幻想乡", "被遗忘之物栖居的边境之地，本作的舞台"),
        ("博丽的巫女", "异变退治者，也就是玩家操纵的自机"),
        ("红魔馆", "矗立湖畔的洋馆，吸血鬼蕾米莉亚的居所"),
        ("关卡 · Stage", "全作三关，每关依次为杂兵波次、中 Boss、关底 Boss"),
        ("符卡 · Spell Card", "东方独有的弹幕规则，一张符卡即一段弹幕式样"),
        ("中 Boss", "波次之后登场的强敌，血量较低，只展开一张符卡"),
        ("关底 Boss", "每关最后的首领，血量高、符卡多，逐张推进"),
        ("弹幕", "符卡铺开的子弹群，全数躲开即为破符"),
        ("自机", "玩家操纵的角色"),
        ("残机", "剩余生命数，本作 3 条，受击减一"),
        ("判定点", "自机唯一的受击点，低速时可见"),
        ("擦弹 · Graze", "敌弹擦过判定点外圈未被击中，可得分"),
        ("灵击 · Spell Card", "消耗一枚符卡，短时无敌并消去身边的弹幕"),
        ("红玉 · POWER", "PWR 标记；火力 +0.05，妖精轮换或 Boss 转阶段掉落"),
        ("青玉 · POINT", "PTS 标记；得分 +500，是妖精最常见的掉落"),
        ("绿玉 · LIFE", "1UP 标记；残机 +1，稀有妖精或最终符卡掉落"),
    )

    # 页面三：按键表
    MANUAL_KEYS = (
        ("方向键 / WASD", "移动自机"),
        ("Shift", "低速移动，判定点收缩，便于穿过弹缝"),
        ("Z", "点按单发，按住连续射击"),
        ("X", "灵击（Bomb）：消去身边弹幕，短时无敌"),
        ("F1", "暂停 / 继续"),
        ("F2", "开关碰撞调试层（判定圆、扫掠线、空间网格）"),
        ("F3", "作弊模式：输入密码后解锁无敌（再次输入关闭）"),
        ("R", "胜负结算后重新开始"),
        ("胜利后 ← / →", "翻阅战绩、后记与鸣谢"),
        ("Enter", "推进对话；胜利后翻页/结束阅读；失败后返回标题"),
        ("Esc", "返回标题；战斗中退出游戏"),
    )
    VICTORY_AFTERWORD_PAGES = (
        (
            "紅霧散去，滿月重新照亮了霧之湖的湖面。",
            "蕾米莉亞仍說，這不過是一場稍有趣味的遊戲，",
            "還抱怨著月亮變回了單調的蒼白色。",
            "",
            "咲夜默默收拾彈痕與碎裂的窗玻璃，",
            "又替主人端來一杯溫熱的紅茶；",
            "美鈴靠在門柱上打盹，帕秋莉則躲回了書架深處。",
            "",
            "「下次，我會準備得更有趣一點。」",
            "吸血鬼的笑聲，隨著紅茶的蒸氣一同消散在夜風裡。",
        ),
        (
            "博麗的巫女沒有收下謝禮，",
            "只確認人里的燈火已重新亮起，便乘風回到神社。",
            "",
            "路上經過霧之湖，冰已化盡，",
            "水面映著滿月，像是什麼都沒發生過。",
            "湖邊的冰之妖精正對著自己的倒影生悶氣，",
            "嘴裡念念有詞地說著「最強」兩個字。",
            "",
            "神社的賽錢箱依舊空空如也——",
            "這件事，倒是從未改變。",
        ),
        (
            "數日之後，紅魔館再度傳出彈幕的聲響。",
            "聽說是館主與圖書館的魔女，為了「紅月亮的最佳觀測角度」",
            "又在院子裡展開了符卡對決。",
            "",
            "人里的孩子們在夕陽下追逐玩耍，",
            "沒有人記得那場被紅霧籠罩的夜晚。",
            "",
            "幻想鄉的異変，大概從來不曾真正完結。",
            "而博麗的巫女，也永遠不會缺下一份工作。",
            "",
            "——紅霧異變，於此落幕。",
        ),
    )
    VICTORY_CREDITS = (
        ("原作", "東方Project / 上海アリス幻樂団"),
        ("音乐", "ZUN"),
        ("曲目来源", "《东方红魔乡》TH06 原作 MIDI"),
        ("素材", "東方紅魔郷（TH06）原作素材"),
        ("制作", "lyra"),
    )
    VICTORY_THANKS = (
        "そして、最後まで遊んでくれた貴方へ。",
        "ありがとう。",
    )

    # 角色图鉴（CG館）：按出场顺序排列。
    # 每条：(立绘键, 显示名, 英文/日文称号, 身份, 介绍段落)
    CG_GALLERY_ENTRIES = (
        (
            "reimu", "博麗靈夢", "Reimu Hakurei",
            "博麗神社的巫女",
            (
                "住在博麗神社的巫女，負責解決幻想鄉的各種異變。",
                "雖然平常看起來有些懶散，實際上彈幕功底紮實，",
                "退治妖怪從不手軟。賽錢箱常年空空如也，",
                "這件事倒是從未改變過。",
            ),
            "靈夢",
        ),
        (
            "rumia", "露米婭", "Rumia",
            "棲息在霧中的黑暗妖怪",
            (
                "操縱黑暗程度的能力的妖怪。",
                "在紅霧彌漫的山麓出沒，以黑暗為掩護偷襲過路人。",
                "個性有些冒失，自稱「最強」的語氣倒是不小，",
                "實力嘛……就當作是夜晚的一點消遣吧。",
            ),
            "露米婭",
        ),
        (
            "cirno", "琪露諾", "Cirno",
            "霧之湖的冰之妖精",
            (
                "住在霧之湖的冰之妖精，自稱「最強」。",
                "能自由操控冰與冷氣，湖面的薄冰便是她的傑作。",
                "個性天真又好勝，最喜歡和過路人較量彈幕。",
                "雖然常常輸，但「最強」二字從未改口。",
            ),
            "琪露諾",
        ),
        (
            "meiling", "紅美鈴", "Hong Meiling",
            "紅魔館的門衛",
            (
                "紅魔館的門衛，中國來的妖怪。",
                "擅長體術與氣功，認真盡責卻常常在值班時打瞌睡。",
                "對闖入者毫不留情，不過偶爾也會放過",
                "看起來不像壞人的客人——雖然事後常被咲夜罵。",
            ),
            "美鈴",
        ),
        (
            "patchouli", "帕秋莉·諾蕾姬", "Patchouli Knowledge",
            "紅魔館圖書館的魔女",
            (
                "紅魔館地下大圖書館的主人，活了百年以上的魔法使。",
                "精通七曜魔法，書庫裡藏著無數禁忌的咒文。",
                "體弱多病，卻能以壓倒性的彈幕量彌補體力的不足。",
                "平時總是埋頭書堆，不太願意見客。",
            ),
            "帕秋莉",
        ),
        (
            "sakuya", "十六夜咲夜", "Sakuya Izayoi",
            "紅魔館的女僕長",
            (
                "紅魔館的女僕長，能操縱時間。",
                "舉止優雅、做事俐落，把整座洋館打理得井然有序。",
                "以小刀為武器，能在一瞬間擲出無數飛刀，",
                "對主人蕾米莉亞絕對忠誠。",
            ),
            "咲夜",
        ),
        (
            "remilia", "蕾米莉亞·斯卡蕾特", "Remilia Scarlet",
            "紅魔館的館主",
            (
                "活了五百年的吸血鬼，紅魔館的館主。",
                "為了看一眼紅色的月亮，用紅霧籠罩了整個幻想鄉。",
                "外表是嬌小的少女，實力卻極為恐怖，",
                "以五張符卡堂堂正正地迎接博麗的巫女。",
            ),
            "蕾米莉亞",
        ),
    )

    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((config.SCREEN_W, config.SCREEN_H))
        pygame.key.stop_text_input()
        pygame.display.set_caption("东方红雾录 · 红雾异变")
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
        # 加载全部 6 行 atlas（每行 2 列：选中/未选中），按菜单项映射取用。
        # atlas 行：0=Game Start, 1=Replay, 2=Player Data, 3=Manual, 4=Config, 5=Quit
        self._menu_atlas_rows = tuple(
            tuple(
                pygame.transform.smoothscale(
                    menu_atlas.subsurface((column * 256, row * 64, 256, 64)),
                    (360, 90),
                )
                for column in (0, 1)
            )
            for row in range(6)
        )
        # 菜单项 → atlas 行映射
        self.MENU_ATLAS_ROW = {
            "开始游戏": 0,
            "紅霧人物録": 2,
            "操作说明": 3,
            "退出游戏": 5,
            "日后谈": 1,
        }

        self.running = True
        self.scene = self.SCENE_TITLE
        self.menu_selection = 0
        self.stage_select_index = 0      # 关卡选择界面当前选中的关卡（0 起）
        self.unlocked_stage = 1          # 已解锁的最高关卡序号（1 起，默认第 1 关）
        self.all_cleared = False         # 是否通关全部关卡（解锁日后谈）
        self.afterword_only = False      # 是否从菜单单独进入日后谈
        self.cg_gallery_index = 0        # 角色图鉴当前选中角色（0 起）
        self.cg_detail_active = False    # 是否进入角色详情页（查看多张 CG）
        self.cg_detail_cg_index = 0      # 详情页中当前查看的 CG 索引
        progress = _load_progress()
        self.unlocked_stage = progress["unlocked"]
        self.all_cleared = progress["all_cleared"]
        self.manual_page = 0          # 说明书当前页：背景 / 用语 / 操作
        self.ending_page = 0
        self.paused = False
        self.god_mode = False
        self.cheat_prompt_active = False    # 是否正在输入作弊密码
        self.cheat_input = ""               # 当前已输入的密码字符
        self.victory = False
        self.game_over = False
        self.lives = config.PLAYER_LIVES
        self.invulnerable_timer = 0.0
        self.focus = False            # 是否处于低速（focus）状态，由 update 写入
        self.bombs = config.PLAYER_BOMB_START   # 灵击（Bomb）存量
        self.bomb_timer = 0.0                   # 灵击无敌/清弹剩余时间

        self.player = Player(
            config.PLAYER_START_X, config.PLAYER_START_Y
        )
        # 关卡推进交给 director；Boss 只在对局中出现，未开打时为 None
        self.director = StageDirector()
        self.boss: Boss | None = None
        self.bullets: list[Bullet] = []
        self.player_shots: list[PlayerShot] = []
        self.fairies: list[Fairy] = []
        self.fairy_kill_count = 0
        self.items: list[Item] = []
        # 空间网格复用同一个实例，每帧 clear 后重新插入，避免反复新建
        self.grid = collision.SpatialGrid(config.SCREEN_W, config.SCREEN_H,
                                          config.GRID_CELL_SIZE)
        self.shooting = False
        self.shoot_requested = False
        self.fire_timer = 0.0
        self.boss_attack_phase = 0          # 当前符卡序号，用于检测换段
        self.spell_timers: list[float] = []  # 各发射器的独立冷却
        self.spell_imperilled = False        # 当前符卡期间是否被击中 / 用过灵击
        self.spell_timed_out = False         # 当前符卡是否因超时结束
        self.spells_captured = 0             # 成功取得的符卡数
        self.spells_failed = 0               # 失败（被击中 / 灵击 / 超时）的符卡数
        self.awarded_clear = 0               # 已发放通关奖励的关卡序号
        self.spell_announce_timer = 0.0      # 符卡名与技能描述的播报倒计时
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
        self.effects: list[Effect] = []
        self.phase_timer = config.BOSS_PHASE_TIME_LIMIT
        self.boss_flash = 0.0            # Boss 受击闪白计时
        self.graze_fx_cooldown = 0.0     # 擦弹特效的节流，避免刷屏
        self.boss_ceremony_timer = 0.0   # 最终 Boss 击破仪式的剩余时间
        self.screen_shake = 0.0          # 屏幕震动幅度（像素）
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

    def _menu_items(self) -> tuple[str, ...]:
        """根据通关状态返回标题菜单项（通关后追加「日后谈」）。"""
        return self.MENU_ITEMS_CLEARED if self.all_cleared else self.MENU_ITEMS

    def _handle_keydown(self, key: int) -> None:
        if self.scene == self.SCENE_TITLE:
            items = self._menu_items()
            if key == pygame.K_UP:
                self.menu_selection = (self.menu_selection - 1) % len(items)
                self.audio.play("menu_move")
            elif key == pygame.K_DOWN:
                self.menu_selection = (self.menu_selection + 1) % len(items)
                self.audio.play("menu_move")
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.audio.play("menu_ok")
                label = items[self.menu_selection]
                if label == "开始游戏":
                    self.stage_select_index = 0
                    self.scene = self.SCENE_STAGE_SELECT
                elif label == "操作说明":
                    self.manual_page = 0
                    self.scene = self.SCENE_CONTROLS
                elif label == "日后谈":
                    self.afterword_only = True
                    self.ending_page = 1       # 从后记页开始翻阅
                    self.scene = self.SCENE_AFTERWORD
                elif label == "紅霧人物録":
                    self.cg_gallery_index = 0
                    self.scene = self.SCENE_CG_GALLERY
                else:
                    self.running = False
            elif key == pygame.K_ESCAPE:
                self.audio.play("menu_cancel")
                self.running = False
            return

        if self.scene == self.SCENE_STAGE_SELECT:
            if key == pygame.K_UP:
                self.stage_select_index = max(0, self.stage_select_index - 1)
                self.audio.play("menu_move")
            elif key == pygame.K_DOWN:
                self.stage_select_index = min(
                    config.STAGE_COUNT - 1, self.stage_select_index + 1
                )
                self.audio.play("menu_move")
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.stage_select_index < self.unlocked_stage:
                    self.audio.play("menu_ok")
                    self._reset_run(self.stage_select_index)
                    self.scene = self.SCENE_PLAYING
                else:
                    self.audio.play("menu_cancel")
            elif key == pygame.K_ESCAPE:
                self.audio.play("menu_cancel")
                self.scene = self.SCENE_TITLE
                self.menu_selection = 0
            return

        if self.scene == self.SCENE_AFTERWORD:
            # 日后谈独立翻阅：沿用 ending_page，覆盖 result/afterword/credits 三页
            min_page = 1 if getattr(self, "afterword_only", False) else 0
            if key in (pygame.K_LEFT, pygame.K_a):
                if self.ending_page > min_page:
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
                    self.afterword_only = False
                    self.scene = self.SCENE_TITLE
            elif key == pygame.K_ESCAPE:
                self.audio.play("menu_cancel")
                self.afterword_only = False
                self.scene = self.SCENE_TITLE
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

        if self.scene == self.SCENE_CG_GALLERY:
            total = len(self.CG_GALLERY_ENTRIES)
            if self.cg_detail_active:
                # 详情页：← → 切换该角色的多张 CG，Esc 返回列表
                entry = self.CG_GALLERY_ENTRIES[self.cg_gallery_index]
                portrait_group = self.art.portraits.get(entry[0])
                cg_count = len(portrait_group) if portrait_group else 1
                if key in (pygame.K_LEFT, pygame.K_a):
                    if self.cg_detail_cg_index > 0:
                        self.cg_detail_cg_index -= 1
                        self.audio.play("menu_move")
                elif key in (pygame.K_RIGHT, pygame.K_d):
                    if self.cg_detail_cg_index < cg_count - 1:
                        self.cg_detail_cg_index += 1
                        self.audio.play("menu_move")
                elif key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.cg_detail_active = False
                    self.cg_detail_cg_index = 0
                    self.audio.play("menu_cancel")
            else:
                # 列表页：← → 切换角色，Enter 进入详情页
                if key in (pygame.K_LEFT, pygame.K_a):
                    if self.cg_gallery_index > 0:
                        self.cg_gallery_index -= 1
                        self.audio.play("menu_move")
                elif key in (pygame.K_RIGHT, pygame.K_d):
                    if self.cg_gallery_index < total - 1:
                        self.cg_gallery_index += 1
                        self.audio.play("menu_move")
                elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.cg_detail_active = True
                    self.cg_detail_cg_index = 0
                    self.audio.play("menu_ok")
                elif key == pygame.K_ESCAPE:
                    self.audio.play("menu_cancel")
                    self.scene = self.SCENE_TITLE
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
            return
        director = getattr(self, "director", None)
        if director is not None and director.waiting_dialogue:
            # 对话进行中：Z / Enter / 空格 先补全本行，再推进到下一句
            if key in (pygame.K_z, pygame.K_RETURN, pygame.K_KP_ENTER,
                       pygame.K_SPACE):
                self.audio.play("menu_move")
                director.advance_dialogue()
            return
        if key == pygame.K_z:
            self.shoot_requested = True
        elif key == pygame.K_x:
            self._use_bomb()
        elif key == pygame.K_F1:
            self.paused = not self.paused
        elif key == pygame.K_F2:
            self.debug_overlay = not self.debug_overlay
        elif key == pygame.K_F3:
            # F3：已开启无敌时直接关闭；未开启时弹出密码输入框
            if getattr(self, "god_mode", False):
                self.god_mode = False
                self.audio.play("menu_cancel")
            else:
                self.cheat_prompt_active = True
                self.cheat_input = ""
                self.audio.play("menu_ok")
            return
        # 作弊密码输入中：只接受数字键
        if getattr(self, "cheat_prompt_active", False):
            if pygame.K_0 <= key <= pygame.K_9:
                self.cheat_input += chr(key)
                self.audio.play("menu_move")
                if len(self.cheat_input) >= len(self.CHEAT_PASSWORD):
                    if self.cheat_input == self.CHEAT_PASSWORD:
                        self.god_mode = not self.god_mode
                        self.audio.play("menu_ok")
                    else:
                        self.audio.play("menu_cancel")
                    self.cheat_prompt_active = False
                    self.cheat_input = ""
            elif key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                self.cheat_prompt_active = False
                self.cheat_input = ""
            return

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

    def _boss_attack_origin(self, boss: Boss) -> Vector2:
        """返回立绘身体处的弹幕发射点，区别于 Boss 立绘的脸部中心。"""
        return boss.pos + Vector2(*config.BOSS_ATTACK_ORIGIN_OFFSET)

    def _spawn_boss(self, spec) -> None:
        """按 director 给出的规格生成 Boss，并复位符卡计时。"""
        self.boss = Boss(config.BOSS_START_X, config.BOSS_START_Y, spec)
        self.boss_attack_phase = 0
        self.spell_timers = []
        self.phase_timer = config.BOSS_PHASE_TIME_LIMIT
        self.boss_flash = 0.0
        self.spell_imperilled = False
        self.spell_timed_out = False
        self.spell_announce_timer = 0.0

    def _spawn_boss_attack(self, boss: Boss, emitter) -> None:
        """铺开一个发射器描述的一轮弹幕。

        形状与角度交给 :func:`spells.emit`，这里只把结果并入弹幕列表，并在
        带有 ``spin`` 的环形 / 螺旋上累加整体相位，让弹幕逐轮旋转起来。
        """
        origin = self._boss_attack_origin(boss)
        self.bullets.extend(spells.emit(
            emitter, self.art, origin, self.player.pos, boss.spell_angle
        ))
        if emitter.spin:
            boss.spell_angle = (
                boss.spell_angle + math.radians(emitter.spin)
            ) % math.tau

    def _update_boss_attacks(self, dt: float) -> None:
        """推进当前符卡：各发射器独立冷却，限时耗尽则强制结束本张符卡。"""
        boss = self.boss
        if boss is None or not boss.alive:
            return

        spell = boss.spell
        if boss.phase != self.boss_attack_phase:
            self._enter_spell(boss, spell, self.phase_timer)

        self.phase_timer = max(0.0, self.phase_timer - dt)
        if self.phase_timer <= 0.0:
            self._force_phase_end()
            return

        for index, emitter in enumerate(spell.emitters):
            self.spell_timers[index] -= dt
            if self.spell_timers[index] > 0.0:
                continue
            self._spawn_boss_attack(boss, emitter)
            self.spell_timers[index] = emitter.interval

    def _enter_spell(self, boss: Boss, spell, remaining: float) -> None:
        """切换到一张符卡：结算上一张的成败，重置计时并按需掉落道具。

        ``remaining`` 是被终结的那张符卡的剩余时间，用于计算时间加成；首张
        符卡没有「上一张」，因此不结算。
        """
        previous = self.boss_attack_phase
        self.boss_attack_phase = boss.phase
        self.spell_timers = spell.cooldowns()
        self.phase_timer = spell.duration
        boss.spell_angle = 0.0
        # 展开新符卡时弹出符卡名与技能描述，贴近原作的符卡宣告
        self.spell_announce_timer = config.SPELL_ANNOUNCE_DURATION
        if previous <= 0:
            return
        self._settle_spell(remaining)
        self.audio.play("phase_change")
        self.effects.append(Effect(
            boss.pos.x, boss.pos.y, self.art.boss_burst,
            config.BURST_DURATION, start_scale=0.3, end_scale=1.0,
        ))
        # 每展开一张新符卡掉一批火力道具；最后一张额外给一个 1UP
        self._spawn_items(
            boss.pos.x, boss.pos.y, "power", config.BOSS_PHASE_DROP_POWER
        )
        if boss.phase == boss.spell_count:
            self._spawn_items(boss.pos.x, boss.pos.y + 44.0, "life", 1)

    def _settle_spell(self, remaining: float) -> None:
        """结算刚结束的一张符卡。

        原作规则：只有在限时内、且全程未被击中也没用灵击，才算「取得」并拿到
        时间加成；被击中、灵击或超时都记为失败，不给分。
        """
        if self.spell_imperilled or self.spell_timed_out:
            self.spells_failed += 1
            self.audio.play("menu_cancel")
        else:
            self.spells_captured += 1
            self.score += (config.BOSS_SPELL_BASE_BONUS
                           + config.BOSS_SPELL_TIME_BONUS
                           * int(max(0.0, remaining)))
            self.audio.play("menu_ok")
        self.spell_imperilled = False
        self.spell_timed_out = False

    def _force_phase_end(self) -> None:
        """符卡倒计时归零：把当前符卡直接推到尽头。

        非最后一张超时即降到本段末尾（转入下一张），最后一张超时视为 Boss
        被击破，与原作「符卡时间到即结束该符卡」的处理一致；超时不结算取得。
        """
        boss = self.boss
        if boss is None:
            return
        self.spell_timed_out = True
        spell_count = boss.spell_count
        segment = boss.max_hp / spell_count
        if boss.phase < spell_count:
            boss.hp = min(
                boss.hp, segment * (spell_count - boss.phase) - 1.0
            )
            self.phase_timer = 0.0
        else:
            boss.hp = 0.0
            boss.alive = False

    def _check_boss_collisions(self) -> None:
        """用相对运动线段检测玩家弹与移动 Boss 的碰撞。"""
        if self.boss is not None and self.boss.alive:
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
        if self.boss is not None and not self.boss.alive:
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
        """击破妖精：按波次指定掉落，缺省时轮换 POINT/POWER 并低概率掉 LIFE。"""
        self.audio.play("enemy_dead")
        self.effects.append(Effect(
            fairy.pos.x, fairy.pos.y, self.art.boss_burst,
            config.BURST_DURATION, start_scale=0.14, end_scale=0.36,
            start_alpha=200, end_alpha=0,
        ))
        self.fairy_kill_count += 1
        if fairy.drop is not None:
            kind = fairy.drop
        elif random.random() < config.FAIRY_LIFE_DROP_CHANCE:
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
        """推进道具：靠近自机时磁吸，越过回收线时全屏吸入，接触后拾取。"""
        collect_all = self.player.pos.y <= config.ITEM_COLLECT_LINE
        for item in self.items:
            if not item.alive:
                continue
            offset = self.player.pos - item.pos
            distance = offset.length()
            if distance == 0.0:
                item.vel = Vector2(0.0, 0.0)
            elif collect_all or distance <= config.ITEM_MAGNET_RADIUS:
                item.vel = offset * (config.ITEM_MAGNET_SPEED / distance)
            else:
                item.vel = Vector2(0.0, config.ITEM_FALL_SPEED)
            item.update(dt)
            if item.alive and item.pos.distance_to(self.player.pos) <= item.radius:
                self._collect_item(item)
        self.items = [item for item in self.items if item.alive]

    def _on_boss_defeated(self) -> None:
        """击破 Boss：结算符卡与分数、播放大爆特效并清空弹幕，随后回报 director。

        中 Boss 只是关卡中的一道关卡，击破后立刻让出场地；关底 Boss 击破后
        由 director 接手推进后续对话、关卡结算与结局。最终关的关底 Boss 击破
        时会触发一段「异变终结」仪式：白闪、震屏、慢动作粒子与大字卡，
        推迟 director 的推进直到仪式播完。
        """
        boss = self.boss
        if boss is None:
            return
        # 最后一张符卡在「换符卡」时不会被结算，这里补上
        self._settle_spell(self.phase_timer)
        self.score += (config.MIDBOSS_SCORE if boss.midboss
                       else config.VICTORY_SCORE)
        self.audio.play("enemy_dead")
        self.effects.append(Effect(
            boss.pos.x, boss.pos.y, self.art.boss_burst,
            config.BURST_DURATION, start_scale=0.4, end_scale=1.3,
        ))
        self.bullets.clear()
        self.player_shots.clear()
        self.boss = None
        self.spell_timers = []
        self.phase_timer = config.BOSS_PHASE_TIME_LIMIT
        self._register_hiscore()

        is_final_boss = (
            not boss.midboss
            and self.director.stage_number >= config.STAGE_COUNT
        )
        if is_final_boss:
            # 最终 Boss 击破仪式：环形爆发 + 多段闪光 + 强震屏
            cx, cy = boss.pos.x, boss.pos.y
            ring_count = 10
            for i in range(ring_count):
                angle = 2.0 * math.pi * i / ring_count
                radius = 70.0
                self.effects.append(Effect(
                    cx + math.cos(angle) * radius,
                    cy + math.sin(angle) * radius,
                    self.art.boss_burst, config.BURST_DURATION * 1.8,
                    start_scale=0.4, end_scale=2.4,
                ))
            for offset in ((-60, -30), (60, -20), (0, 40), (-40, 50), (50, 30)):
                self.effects.append(Effect(
                    boss.pos.x + offset[0], boss.pos.y + offset[1],
                    self.art.boss_burst, config.BURST_DURATION * 1.6,
                    start_scale=0.5, end_scale=2.2,
                ))
            self.boss_ceremony_timer = 3.6
            self.screen_shake = 18.0
            return
        director = getattr(self, "director", None)
        if director is not None:
            director.notify_boss_defeated()

    def _register_hiscore(self) -> None:
        """刷新并持久化最高分（无写权限时静默忽略）。"""
        if self.score > self.hiscore:
            self.hiscore = self.score
            _save_hiscore(self.hiscore)

    def _reset_run(self, stage_index: int = 0) -> None:
        """从头开始一局：复位 director 与全部战斗状态。

        ``stage_index`` 为 0 起的关卡序号，决定从哪一关开始；关卡选择界面
        据此让玩家重玩已解锁的任意一关。
        """
        self.player = Player(config.PLAYER_START_X, config.PLAYER_START_Y)
        self.boss = None
        self.bullets.clear()
        self.player_shots.clear()
        self.grid.clear()
        self.shooting = False
        self.shoot_requested = False
        self.fire_timer = 0.0
        self.boss_attack_phase = 0
        self.spell_timers = []
        self.spell_imperilled = False
        self.spell_timed_out = False
        self.spells_captured = 0
        self.spells_failed = 0
        self.awarded_clear = 0
        self.spell_announce_timer = 0.0
        self.graze_total = 0
        self.hit_total = 0
        self.hit_flash = 0.0
        self.score = 0                 # 单局分数重置，最高分保留
        self.power = config.PLAYER_POWER_START
        self.item_total = 0
        self.effects.clear()
        self.items.clear()
        self.fairies.clear()
        self.fairy_kill_count = 0
        self.phase_timer = config.BOSS_PHASE_TIME_LIMIT
        self.boss_flash = 0.0
        self.graze_fx_cooldown = 0.0
        self.boss_ceremony_timer = 0.0
        self.screen_shake = 0.0
        self.lives = config.PLAYER_LIVES
        self.invulnerable_timer = 0.0
        self.bombs = config.PLAYER_BOMB_START
        self.bomb_timer = 0.0
        self.focus = False
        self.paused = False
        self.victory = False
        self.ending_page = 0
        self.game_over = False
        self.scene = self.SCENE_PLAYING
        self.animation_timer = 0.0
        self.director = StageDirector(start_stage=stage_index)
        self.director.reset()
        self.director.start()

    def _use_bomb(self) -> None:
        """灵击（Bomb）：消耗一枚符卡，清去身边弹幕并获得短暂无敌。

        与「被击中即清屏」不同，这是玩家主动的保命手段：消去的子弹会折算
        分数，并少量化作点数道具，用来换取有限的火力补给。
        """
        if (self.bombs <= 0 or self.bomb_timer > 0.0
                or self.game_over or self.victory or self.paused):
            return
        self.bombs -= 1
        self.bomb_timer = config.PLAYER_BOMB_DURATION
        self.invulnerable_timer = max(
            self.invulnerable_timer, config.PLAYER_BOMB_DURATION
        )
        # 用灵击保命，代价是当前符卡失去「取得」资格
        self.spell_imperilled = True
        self.audio.play("phase_change")
        self.effects.append(Effect(
            self.player.pos.x, self.player.pos.y, self.art.boss_burst,
            config.BURST_DURATION, start_scale=0.25, end_scale=1.7,
            start_alpha=190, end_alpha=0,
        ))
        cleared, kept = 0, []
        for bullet in self.bullets:
            if bullet.pos.distance_to(self.player.pos) <= config.PLAYER_BOMB_RADIUS:
                cleared += 1
            else:
                kept.append(bullet)
        self.bullets = kept
        self.score += cleared * config.PLAYER_BOMB_BULLET_SCORE
        drops = min(cleared // 4, config.PLAYER_BOMB_CLEAR_ITEM_CAP)
        if drops > 0:
            self._spawn_items(
                self.player.pos.x, self.player.pos.y, "point", drops
            )

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
        # 被击中会让当前符卡失去「取得」资格
        if self.boss is not None and self.boss.alive:
            self.spell_imperilled = True
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
            # 本局到此结束：失败局的新高分同样要写入存档
            self._register_hiscore()
        else:
            self.invulnerable_timer = config.PLAYER_INVULNERABLE_TIME

    def _advance_effects(self, dt: float) -> None:
        """推进所有一次性特效，并回收播完的实例。"""
        for effect in self.effects:
            effect.update(dt)
        self.effects = [effect for effect in self.effects if effect.alive]

    def _update_fairies(self, dt: float) -> None:
        """推进杂兵并回收出屏者；带弹型的杂兵在场地内按冷却开火。

        妖精的生成时机不再由计时器决定，而是由 :class:`~src.director.StageDirector`
        按关卡波次脚本投放，这里只负责推进与回收，和原作「编队压上」一致。
        """
        fired: list[Bullet] = []
        for fairy in self.fairies:
            fairy.update(dt)
            if (fairy.attack is not None and fairy.alive
                    and fairy.state != "leave"
                    and fairy.pos.y >= config.PLAYFIELD_TOP
                    and fairy.fire_timer <= 0.0):
                fired.extend(spells.emit(
                    fairy.attack, self.art, fairy.pos, self.player.pos
                ))
                fairy.fire_timer = fairy.attack.interval
        if fired:
            self.bullets.extend(fired)
        self.fairies = [fairy for fairy in self.fairies if fairy.alive]

    def _update_music(self) -> None:
        """按当前场景与流程状态切换循环背景音乐；同一首不会被打断重来。

        每个关卡与每个 Boss 都有独立的 TH06 原作曲目；若 MIDI 不可用则
        自动降级到旧版 PC-98 OGG。
        """
        if self.scene == self.SCENE_STAGE_SELECT:
            self.audio.play_music("stage_select")
            return
        if self.scene in (self.SCENE_TITLE, self.SCENE_CONTROLS):
            self.audio.play_music("title")
            return
        if self.scene == self.SCENE_CG_GALLERY:
            self.audio.play_music("ending")
            return
        if self.scene == self.SCENE_AFTERWORD:
            if getattr(self, "ending_page", 0) >= len(self.ENDING_PAGES) - 1:
                self.audio.play_music("credits")
            else:
                self.audio.play_music("ending")
            return
        if self.scene != self.SCENE_PLAYING:
            return
        if self.victory:
            # 胜利流程：afterword 用结局曲，credits 用鸣谢曲
            if getattr(self, "ending_page", 0) >= len(self.ENDING_PAGES) - 1:
                self.audio.play_music("credits")
            else:
                self.audio.play_music("ending")
            return
        # 最终 Boss 击破仪式：播 U.N.OWEN 这首最知名的东方曲
        if getattr(self, "boss_ceremony_timer", 0.0) > 0.0:
            self.audio.play_music("ceremony")
            return
        director = getattr(self, "director", None)
        if director is None:
            return
        # Boss 战：按 Boss 切换专属曲目
        if director.state == FIGHT and self.boss is not None:
            key = self.boss.spec.key
            boss_music = {
                "rumia": "boss_rumia",
                "cirno": "boss_cirno",
                "remilia": "boss_remilia",
            }.get(key)
            if boss_music:
                self.audio.play_music(boss_music)
                return
        # 非战斗：按关卡切换关卡曲
        stage_music = {1: "stage1", 2: "stage2", 3: "stage3"}.get(
            director.stage_number, "stage1"
        )
        self.audio.play_music(stage_music)

    def update(self, dt: float) -> None:
        self._update_music()
        if self.scene != self.SCENE_PLAYING:
            return
        if self.paused or getattr(self, "cheat_prompt_active", False):
            self.shoot_requested = False
            return
        if self.victory or self.game_over:
            # 结算画面仍需让特效播完、红屏闪烁淡出
            self.shoot_requested = False
            self._advance_effects(dt)
            self.hit_flash = max(0.0, self.hit_flash - dt)
            return

        self._advance_effects(dt)
        self.boss_flash = max(0.0, self.boss_flash - dt)
        self.bomb_timer = max(0.0, self.bomb_timer - dt)

        # 最终 Boss 击破仪式：白闪消退、震屏衰减、慢动作播放粒子，结束后才推进剧情
        if getattr(self, "boss_ceremony_timer", 0.0) > 0.0:
            ceremony_dt = dt * 0.35          # 慢动作：粒子以 35% 速度推进
            for effect in self.effects:
                effect.update(ceremony_dt)
            self.boss_ceremony_timer = max(0.0, self.boss_ceremony_timer - dt)
            self.screen_shake = max(0.0, self.screen_shake - dt * 40.0)
            self.shoot_requested = False
            if self.boss_ceremony_timer <= 0.0:
                self.screen_shake = 0.0
                director = getattr(self, "director", None)
                if director is not None:
                    director.notify_boss_defeated()
            return

        # 关卡推进：过场 / 对话 / 波次 / 战斗 / 结算全由 director 编排
        self.fairies.extend(
            self.director.update(dt, len(self.fairies))
        )
        spec = self.director.take_boss()
        if spec is not None:
            self._spawn_boss(spec)
        if self.director.cleared_stage > self.awarded_clear:
            # 每通过一关发一次通关奖励（原作「ステージクリア」结算）
            self.awarded_clear = self.director.cleared_stage
            self.score += config.STAGE_CLEAR_BONUS
        if self.director.completed:
            # 单关结束：解锁下一关并保存进度；最终关才进入结局
            cleared = self.director.stage_number
            if cleared >= self.unlocked_stage and cleared < config.STAGE_COUNT:
                self.unlocked_stage = cleared + 1
            if cleared >= config.STAGE_COUNT:
                self.all_cleared = True
            _save_progress(self.unlocked_stage, self.all_cleared)
            self._register_hiscore()
            if cleared >= config.STAGE_COUNT:
                self.victory = True
            else:
                self.stage_select_index = min(
                    self.stage_select_index, self.unlocked_stage - 1
                )
                self.scene = self.SCENE_STAGE_SELECT
            return
        if self.director.state in (BANNER, TALK):
            # 过场与对话期间冻结弹幕场，只让已有效果播完
            self.shoot_requested = False
            return

        self.invulnerable_timer = max(0.0, self.invulnerable_timer - dt)
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

        if self.boss is not None and self.boss.alive:
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
        if self.spell_announce_timer > 0.0:
            self.spell_announce_timer = max(0.0, self.spell_announce_timer - dt)
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
        if self.scene == self.SCENE_STAGE_SELECT:
            self._draw_stage_select()
            return
        if self.scene == self.SCENE_AFTERWORD:
            self._draw_afterword_view()
            return
        if self.scene == self.SCENE_CG_GALLERY:
            self._draw_cg_gallery()
            return

        field_origin = (config.PLAYFIELD_LEFT, config.PLAYFIELD_TOP)
        self.screen.blit(self.art.scene_background, (0, 0))
        backgrounds = self.art.stage_backgrounds
        background_index = min(
            self.director.background_index, len(backgrounds) - 1
        )
        self.screen.blit(backgrounds[background_index], field_origin)
        self.screen.blit(self.playfield_shade, field_origin)
        self.screen.blit(self.field_vignette, field_origin)

        for fairy in self.fairies:
            fairy.draw(
                self.screen,
                self.art.enemy_frames.get(fairy.frames_key)
                or self.art.fairy_frames,
                flash=fairy.hit_flash / config.BOSS_FLASH_DURATION,
            )

        for item in self.items:
            item.draw(self.screen, self.art.item_halo)

        boss = self.boss
        if boss is not None and boss.alive:
            boss_sprite = self._boss_sprite(boss)
            if self.boss_flash > 0.0:
                boss_sprite = _flash_sprite(
                    boss_sprite, self.boss_flash / config.BOSS_FLASH_DURATION
                )
            boss.draw(self.screen, boss_sprite)

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
        self._draw_spell_announcement()
        self._draw_hud()

        director = self.director
        if self.paused:
            self._draw_pause_card()
        elif self.game_over:
            self._draw_ending(self.art.ending_defeat, victory=False)
        elif self.victory:
            ending_background = self._ending_background_for_page(self.ending_page)
            self._draw_ending(ending_background, victory=True)
        elif director.state == BANNER:
            self._draw_banner_card()
        elif director.waiting_dialogue and director.dialogue is not None:
            director.dialogue.draw(
                self.screen, self.art, self.font, self.font_big
            )

        # 最终 Boss 击破仪式：震屏 + 白闪 + 「異変終結」大字卡
        if self.boss_ceremony_timer > 0.0:
            self._apply_screen_shake()
            self._draw_boss_ceremony()

        # 作弊密码输入框始终置顶
        if self.cheat_prompt_active:
            self._draw_cheat_prompt()

    def _boss_sprite(self, boss: Boss) -> pygame.Surface:
        """取当前 Boss 的立绘：按角色键取一组表情，再按符卡序号选一张。"""
        group = self.art.hud_portraits.get(boss.spec.key)
        if not group:
            group = self.art.boss_faces
        return group[min(boss.phase, len(group)) - 1]

    def _draw_ornate_panel(self, rect: pygame.Rect) -> None:
        """绘制半透明双线描金卡片，底图始终保留原作素材。"""
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((10, 5, 12, 236))
        self.screen.blit(panel, rect.topleft)
        pygame.draw.rect(self.screen, config.GOLD, rect, 2)
        pygame.draw.rect(self.screen, (120, 68, 54), rect.inflate(-14, -14), 1)

    def _apply_screen_shake(self) -> None:
        """将整屏内容随机偏移，模拟击破最终 Boss 时的震屏。"""
        magnitude = self.screen_shake
        if magnitude <= 0.0:
            return
        dx = random.uniform(-magnitude, magnitude)
        dy = random.uniform(-magnitude, magnitude)
        snapshot = self.screen.copy()
        self.screen.fill(config.BLACK)
        self.screen.blit(snapshot, (round(dx), round(dy)))

    def _draw_boss_ceremony(self) -> None:
        """最终 Boss 击破仪式：白闪 + 赤红闪 + 「異変終結」大字卡 + 全符卡破却。"""
        field = pygame.Rect(
            config.PLAYFIELD_LEFT, config.PLAYFIELD_TOP,
            config.PLAYFIELD_WIDTH, config.PLAYFIELD_HEIGHT,
        )
        total = 3.6
        t = self.boss_ceremony_timer
        elapsed = total - t

        # 第一段：白闪（前 0.5 秒全白，之后渐隐）
        flash_t = max(0.0, t - (total - 0.5))
        flash_alpha = min(255, int(255 * flash_t / 0.5))
        if flash_alpha > 0:
            white = pygame.Surface(field.size, pygame.SRCALPHA)
            white.fill((255, 250, 240, flash_alpha))
            self.screen.blit(white, field.topleft)

        # 第二段：赤红闪（仪式中段，约 1.6s ~ 2.2s 处浮现）
        red_flash = 0.0
        if 1.6 <= elapsed <= 2.2:
            if elapsed < 1.9:
                red_flash = (elapsed - 1.6) / 0.3
            else:
                red_flash = (2.2 - elapsed) / 0.3
        red_alpha = int(180 * max(0.0, min(1.0, red_flash)))
        if red_alpha > 0:
            red = pygame.Surface(field.size, pygame.SRCALPHA)
            red.fill((200, 30, 40, red_alpha))
            self.screen.blit(red, field.topleft)

        # 文字卡：仪式中段浮现，后段淡出
        if 0.4 < t < total - 0.3:
            fade_in = min(1.0, (total - 0.3 - t) / 0.5)
            fade_out = min(1.0, t / 0.6)
            alpha = int(255 * min(fade_in, fade_out))
            cx = config.PLAYFIELD_LEFT + config.PLAYFIELD_WIDTH // 2
            cy = config.PLAYFIELD_TOP + config.PLAYFIELD_HEIGHT // 2

            title = self.font_big.render("異変終結", True, config.PALE_GOLD)
            title.set_alpha(alpha)
            shadow = self.font_big.render("異変終結", True, config.BLACK)
            shadow.set_alpha(alpha)
            self.screen.blit(shadow, shadow.get_rect(center=(cx + 3, cy + 3)))
            self.screen.blit(title, title.get_rect(center=(cx, cy)))

            sub = self.font.render(
                "INCIDENT RESOLVED  /  紅霧散去", True, config.WHITE,
            )
            sub.set_alpha(alpha)
            self.screen.blit(sub, sub.get_rect(center=(cx, cy + 56)))

            # 全符卡破却：在赤红闪之后浮现
            if elapsed > 2.0:
                broken_alpha = int(255 * min(1.0, (elapsed - 2.0) / 0.4))
                broken = self.font.render(
                    "全符卡破却  /  ALL SPELL CARDS BROKEN", True, config.GOLD,
                )
                broken.set_alpha(min(alpha, broken_alpha))
                self.screen.blit(broken, broken.get_rect(center=(cx, cy + 100)))

    def _draw_cheat_prompt(self) -> None:
        """作弊密码输入框：居中卡片，显示已输入的数字（用●遮掩）。"""
        panel = pygame.Rect(config.SCREEN_W // 2 - 260, config.SCREEN_H // 2 - 90,
                            520, 180)
        self._draw_ornate_panel(panel)
        cx = panel.centerx
        self.screen.blit(
            self.font.render("異變調查員認證  /  CHEAT CODE", True, config.MUTED),
            self.font.render("異變調查員認證  /  CHEAT CODE", True, config.MUTED
                             ).get_rect(center=(cx, panel.top + 40)),
        )
        # 密码用 ● 遮掩，已输入位数高亮
        pwd_len = len(self.CHEAT_PASSWORD)
        masked = " ".join("●" if i < len(self.cheat_input) else "○"
                          for i in range(pwd_len))
        self.screen.blit(
            self.font_big.render(masked, True, config.PALE_GOLD),
            self.font_big.render(masked, True, config.PALE_GOLD
                                 ).get_rect(center=(cx, panel.top + 100)),
        )
        self.screen.blit(
            self.font.render("输入 6 位密码  ·  Esc 取消", True, config.WHITE),
            self.font.render("输入 6 位密码  ·  Esc 取消", True, config.WHITE
                             ).get_rect(center=(cx, panel.bottom - 36)),
        )

    def _draw_banner_card(self) -> None:
        """关卡标题过场：以横幅卡片呈现本关的舞台、中 Boss 与首领。"""
        banner = self.director.banner
        if banner is None:
            return
        self.screen.blit(self.entry_shade, (0, 0))

        panel = pygame.Rect(158, 244, 964, 472)
        self._draw_ornate_panel(panel)
        left = panel.left + 48
        self.screen.blit(
            self.font.render(
                f"異変調査記録  /  INCIDENT FILE {banner.stage_index:02d}",
                True, config.MUTED,
            ),
            (left, panel.top + 38),
        )
        self.screen.blit(
            self.font_big.render(banner.title, True, config.PALE_GOLD),
            (left, panel.top + 88),
        )
        self.screen.blit(
            self.font.render(banner.subtitle, True, config.WHITE),
            (left, panel.top + 148),
        )
        pygame.draw.line(
            self.screen, config.GOLD,
            (left, panel.top + 198), (panel.right - 48, panel.top + 198), 1,
        )
        script = self.director.script
        rows: list[tuple[str, str]] = []
        if script is not None:
            rows.append(("中首領  /  MIDBOSS",
                         script.midboss.title if script.midboss else "（無）"))
            rows.append(("首領  /  BOSS", script.boss.title))
            rows.append(("符卡  /  SPELL CARD",
                         f"{len(script.boss.spells)} 張"))
        for index, (label, value) in enumerate(rows):
            y = panel.top + 222 + index * 44
            self.screen.blit(
                self.font.render(label, True, config.PALE_GOLD), (left, y)
            )
            self.screen.blit(
                self.font.render(value, True, config.WHITE),
                (left + 260, y),
            )

        if script is not None:
            portrait_group = self.art.hud_portraits.get(script.boss.key) or ()
            if portrait_group:
                portrait = portrait_group[0]
                self.screen.blit(
                    portrait,
                    portrait.get_rect(
                        midright=(panel.right - 54, panel.centery + 8)
                    ),
                )

        self.screen.blit(
            self.font.render("避開彈幕，破除符卡。", True, config.PALE_GOLD),
            (left, panel.bottom - 62),
        )

    def _draw_ending(self, background: pygame.Surface, victory: bool) -> None:
        """結算回顾：原作插图、关卡进度、战绩与再战指引。"""
        self.screen.blit(background, (0, 0))
        self.screen.blit(self.ending_shade, (0, 0))
        panel = pygame.Rect(120, 128, 1040, 704)
        self._draw_ornate_panel(panel)
        left = panel.left + 58
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
        total_stages = max(1, len(self.director.stages))
        stage_no = min(max(self.director.stage_number, 1), total_stages)
        self.screen.blit(
            self.font.render("紅霧異変  /  紅魔館異聞", True, config.PALE_GOLD),
            (left, panel.top + 184),
        )
        if victory:
            progress = f"全 {total_stages} 關  /  ALL STAGES CLEARED"
        else:
            progress = f"到達  /  STAGE {stage_no} / {total_stages}"
            if self.boss is not None:
                progress += f"  「{self.boss.spell.name}」"
        self.screen.blit(
            self.font.render(progress, True, config.WHITE),
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
        self.screen.blit(
            self.font.render(
                f"符卡取得  {self.spells_captured}    失敗  {self.spells_failed}",
                True, config.PALE_GOLD,
            ),
            (left, panel.top + 398),
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
        afterword_count = len(self.VICTORY_AFTERWORD_PAGES)
        is_afterword = 1 <= page <= afterword_count
        is_credits = page == len(self.ENDING_PAGES) - 1

        if is_afterword:
            title = "後記"
            subtitle = f"AFTERWORD  /  異変のあと  {page} / {afterword_count}"
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

        if is_afterword:
            # 每页日后谈配一张角色立绘，营造原作 CG 感（右侧底部对齐）。
            afterword_index = page - 1
            if 0 <= afterword_index < len(self.AFTERWORD_PAGE_VISUALS):
                _, portrait_key, portrait_idx = self.AFTERWORD_PAGE_VISUALS[
                    afterword_index
                ]
                portraits = self.art.portraits.get(portrait_key)
                if portraits and 0 <= portrait_idx < len(portraits):
                    portrait = portraits[portrait_idx]
                    px = panel.right - 40 - portrait.get_width()
                    py = panel.bottom - 120 - portrait.get_height()
                    # 立绘下方加一层柔光，让角色从深色卡片中浮起。
                    glow = pygame.Surface(
                        (portrait.get_width() + 40, portrait.get_height() + 40),
                        pygame.SRCALPHA,
                    )
                    pygame.draw.ellipse(
                        glow, (120, 68, 54, 55), glow.get_rect().inflate(-6, -6)
                    )
                    self.screen.blit(
                        glow, (px - 20, py - 20),
                    )
                    self.screen.blit(portrait, (px, py))

            y = panel.top + 194
            for line in self.VICTORY_AFTERWORD_PAGES[page - 1]:
                if line:
                    self.screen.blit(
                        self.font.render(line, True, config.WHITE), (left, y)
                    )
                    y += 38
                else:
                    y += 22
            if page == 1:
                hint = "← 戰績  ·  → / Enter 下一頁  ·  R 再戰  ·  Esc 標題"
            elif page == afterword_count:
                hint = "← 上一頁  ·  → / Enter 謝辞  ·  R 再戰  ·  Esc 標題"
            else:
                hint = "← 上一頁  ·  → / Enter 下一頁  ·  R 再戰  ·  Esc 標題"
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
        if self.boss is not None:
            spell_text = (
                f"{self.boss.spec.title}  "
                f"第 {self.boss.phase} 符卡 「{self.boss.spell.name}」"
                f"  {self.boss.phase} / {self.boss.spell_count}"
            )
        else:
            spell_text = "雜兵波次進行中"
        self._draw_center_text(
            spell_text, config.WHITE, font=self.font,
            y=panel.top + 192, center_x=center_x,
        )
        self._draw_center_text(
            "F1 继续弹幕  ·  Esc 退出异变调查",
            config.PALE_GOLD, font=self.font,
            y=panel.top + 258, center_x=center_x,
        )

    def _draw_stage_select(self) -> None:
        """关卡选择界面：列出三关，锁定的关显示锁形，当前选中高亮。"""
        self.screen.blit(self.title_background, (0, 0))
        self.screen.blit(self.title_shade, (0, 0))

        panel = pygame.Rect(220, 120, config.SCREEN_W - 440, config.SCREEN_H - 240)
        self._draw_ornate_panel(panel)
        left = panel.left + 48
        right = panel.right - 48

        self.screen.blit(
            self.font_big.render("選擇關卡", True, config.PALE_GOLD),
            (left, panel.top + 36),
        )
        self.screen.blit(
            self.font.render("SELECT STAGE  /  紅霧異変", True, config.MUTED),
            (left, panel.top + 100),
        )
        pygame.draw.line(
            self.screen, config.GOLD,
            (left, panel.top + 148), (right, panel.top + 148), 1,
        )

        row_h = 132
        start_y = panel.top + 184
        for index in range(config.STAGE_COUNT):
            unlocked = index < self.unlocked_stage
            selected = index == self.stage_select_index
            y = start_y + index * row_h
            row = pygame.Rect(left, y, right - left, row_h - 16)

            if selected:
                sel = pygame.Surface(row.size, pygame.SRCALPHA)
                sel.fill((92, 20, 34, 180))
                self.screen.blit(sel, row.topleft)
            pygame.draw.rect(self.screen, config.GOLD, row, 1 if selected else 0)

            # 关卡编号
            self.screen.blit(
                self.font_big.render(
                    f"{index + 1:02d}",
                    True, config.PALE_GOLD if unlocked else config.GRAY,
                ),
                (row.left + 24, row.top + 18),
            )
            # 标题与副标题
            title_color = config.WHITE if unlocked else config.GRAY
            self.screen.blit(
                self.font.render(
                    self.STAGE_TITLES[index], True, title_color,
                ),
                (row.left + 110, row.top + 22),
            )
            self.screen.blit(
                self.font.render(
                    self.STAGE_SUBTITLES[index], True, config.MUTED,
                ),
                (row.left + 110, row.top + 58),
            )
            # Boss 名
            boss_color = config.PALE_GOLD if unlocked else config.GRAY
            self.screen.blit(
                self.font.render(
                    f"首領  /  {self.STAGE_BOSS_NAMES[index]}",
                    True, boss_color,
                ),
                (row.left + 110, row.top + 90),
            )
            # 锁定标记
            if not unlocked:
                lock = self.font.render("🔒 LOCKED", True, config.GRAY)
                self.screen.blit(
                    lock, lock.get_rect(midright=(row.right - 24, row.centery)),
                )
            elif selected:
                arrow = self.font.render("▶ ENTER", True, config.PALE_GOLD)
                self.screen.blit(
                    arrow, arrow.get_rect(midright=(row.right - 24, row.centery)),
                )

        pygame.draw.line(
            self.screen, (120, 68, 54),
            (left, panel.bottom - 96), (right, panel.bottom - 96), 1,
        )
        hint = "↑ ↓ 選擇關卡    Enter 開始    Esc 返回標題"
        self.screen.blit(
            self.font.render(hint, True, config.WHITE),
            (left, panel.bottom - 64),
        )

    def _draw_afterword_view(self) -> None:
        """从菜单进入的日后谈翻阅：复用结局页面的渲染逻辑。"""
        ending_background = self._ending_background_for_page(self.ending_page)
        self._draw_ending(ending_background, victory=True)

    def _draw_cg_gallery(self) -> None:
        """紅霧人物録：列表态浏览角色，详情态查看该角色的多张 CG。"""
        self.screen.blit(self.title_background, (0, 0))
        self.screen.blit(self.ending_shade, (0, 0))

        panel = pygame.Rect(60, 60, config.SCREEN_W - 120, config.SCREEN_H - 120)
        self._draw_ornate_panel(panel)
        left = panel.left + 40
        right = panel.right - 40

        entry = self.CG_GALLERY_ENTRIES[self.cg_gallery_index]
        portrait_key, name, en_name, role, lines, short_name = entry
        portrait_group = self.art.portraits.get(portrait_key)
        is_detail = self.cg_detail_active
        cg_count = len(portrait_group) if portrait_group else 1
        cg_index = min(self.cg_detail_cg_index, cg_count - 1) if is_detail else 0

        # 标题区
        if is_detail:
            title_text = name
            sub_text = f"CG 詳情  /  {en_name}"
        else:
            title_text = "紅霧人物録"
            sub_text = "CHARACTER RECORD  /  登場人物図鑑"
        self.screen.blit(
            self.font_big.render(title_text, True, config.PALE_GOLD),
            (left, panel.top + 32),
        )
        self.screen.blit(
            self.font.render(sub_text, True, config.MUTED),
            (left, panel.top + 96),
        )
        if is_detail:
            counter = self.font.render(
                f"CG {cg_index + 1} / {cg_count}", True, config.PALE_GOLD
            )
        else:
            counter = self.font.render(
                f"{self.cg_gallery_index + 1} / {len(self.CG_GALLERY_ENTRIES)}",
                True, config.PALE_GOLD,
            )
        self.screen.blit(
            counter, counter.get_rect(topright=(right, panel.top + 56))
        )
        pygame.draw.line(
            self.screen, config.GOLD,
            (left, panel.top + 138), (right, panel.top + 138), 1,
        )

        # 左侧：大立绘 + 装饰画框
        portrait = portrait_group[cg_index] if portrait_group else None
        if portrait is not None:
            gallery_h = 470
            pw = max(1, round(portrait.get_width() * gallery_h / portrait.get_height()))
            big_portrait = pygame.transform.smoothscale(portrait, (pw, gallery_h))

            frame_pad = 18
            frame_rect = pygame.Rect(0, 0, pw + frame_pad * 2, gallery_h + frame_pad * 2)
            frame_rect.midleft = (left + 8, panel.centery + 10)

            glow = pygame.Surface(
                (frame_rect.width + 60, frame_rect.height + 60), pygame.SRCALPHA
            )
            pygame.draw.ellipse(
                glow, (140, 78, 50, 70), glow.get_rect().inflate(-10, -10)
            )
            self.screen.blit(glow, glow.get_rect(center=frame_rect.center))
            frame_bg = pygame.Surface(frame_rect.size, pygame.SRCALPHA)
            frame_bg.fill((18, 8, 14, 235))
            self.screen.blit(frame_bg, frame_rect.topleft)
            pygame.draw.rect(self.screen, config.GOLD, frame_rect, 2)
            pygame.draw.rect(
                self.screen, (120, 68, 54), frame_rect.inflate(-8, -8), 1
            )
            self.screen.blit(
                big_portrait, big_portrait.get_rect(center=frame_rect.center)
            )

        # 右侧：人物名、英文名、身份、介绍
        text_left = panel.left + 560
        text_right = right
        y = panel.top + 176

        self.screen.blit(self.font_big.render(name, True, config.PALE_GOLD), (text_left, y))
        y += 62
        self.screen.blit(self.font.render(en_name, True, config.MUTED), (text_left, y))
        y += 36
        self.screen.blit(self.font.render(f"【{role}】", True, config.GOLD), (text_left, y))
        y += 56
        pygame.draw.line(
            self.screen, (120, 68, 54),
            (text_left, y), (text_right, y), 1,
        )
        y += 32
        for line in lines:
            surf = self.font.render(line, True, config.WHITE)
            self.screen.blit(surf, (text_left, y))
            y += 40

        # 底部缩略图条
        thumb_h = 86
        thumb_area_top = panel.bottom - 140
        pygame.draw.line(
            self.screen, (120, 68, 54),
            (left, thumb_area_top - 16), (right, thumb_area_top - 16), 1,
        )

        if is_detail:
            # 详情态：显示该角色的所有表情 CG
            thumb_count = cg_count
            thumb_w = 70
            gap = 14
            total_w = thumb_count * thumb_w + (thumb_count - 1) * gap
            start_x = panel.centerx - total_w // 2
            for i in range(thumb_count):
                tx = start_x + i * (thumb_w + gap)
                ty = thumb_area_top
                tframe = pygame.Rect(tx, ty, thumb_w, thumb_h)
                active = i == cg_index
                tbg = pygame.Surface(tframe.size, pygame.SRCALPHA)
                tbg.fill((92, 20, 34, 210) if active else (10, 5, 12, 180))
                self.screen.blit(tbg, tframe.topleft)
                pygame.draw.rect(
                    self.screen, config.GOLD if active else (80, 50, 40),
                    tframe, 2,
                )
                if portrait_group:
                    thumb = pygame.transform.smoothscale(
                        portrait_group[i],
                        (max(1, round(portrait_group[i].get_width() * thumb_h / portrait_group[i].get_height())), thumb_h),
                    )
                    self.screen.blit(thumb, thumb.get_rect(center=tframe.center))
                label = self.font.render(
                        f"{i + 1}", True, config.PALE_GOLD if active else config.MUTED
                    )
                self.screen.blit(
                        label, label.get_rect(midtop=(tframe.centerx, tframe.bottom + 6))
                    )
            hint = "← →  切換表情     Esc 返回列表"
        else:
            # 列表态：显示所有角色，缩略图下方用短名避免重叠
            thumb_count = len(self.CG_GALLERY_ENTRIES)
            thumb_w = 72
            gap = 64
            total_w = thumb_count * thumb_w + (thumb_count - 1) * gap
            start_x = panel.centerx - total_w // 2
            for i, (pkey, pname, _, _, _, pshort) in enumerate(self.CG_GALLERY_ENTRIES):
                tx = start_x + i * (thumb_w + gap)
                ty = thumb_area_top
                tframe = pygame.Rect(tx, ty, thumb_w, thumb_h)
                active = i == self.cg_gallery_index
                tbg = pygame.Surface(tframe.size, pygame.SRCALPHA)
                tbg.fill((92, 20, 34, 210) if active else (10, 5, 12, 180))
                self.screen.blit(tbg, tframe.topleft)
                pygame.draw.rect(
                    self.screen, config.GOLD if active else (80, 50, 40),
                    tframe, 2,
                )
                pgroup = self.art.portraits.get(pkey)
                if pgroup:
                    thumb = pygame.transform.smoothscale(
                        pgroup[0],
                        (max(1, round(pgroup[0].get_width() * thumb_h / pgroup[0].get_height())), thumb_h),
                    )
                    self.screen.blit(thumb, thumb.get_rect(center=tframe.center))
                name_label = self.font.render(
                        pshort, True, config.PALE_GOLD if active else config.MUTED
                    )
                self.screen.blit(
                    name_label,
                    name_label.get_rect(midtop=(tframe.centerx, tframe.bottom + 6)),
                )
            hint = "← →  切換角色     Enter 查看 CG     Esc 返回標題"

        self.screen.blit(
            self.font.render(hint, True, config.WHITE),
            (left, panel.bottom - 36),
        )


    # 每页日后谈对应的背景与立绘：营造原作 CG 感，而非纯文本。
    AFTERWORD_PAGE_VISUALS = (
        ("scene", "remilia", 0),   # 第1页：红魔馆内，蕾米莉亚
        ("afterword", "cirno", 0), # 第2页：雾之湖畔，琪露诺
        ("victory", "sakuya", 0),  # 第3页：红魔馆日常，咲夜
    )

    def _ending_background_for_page(self, page: int) -> pygame.Surface:
        """按结局页码选择背景图：result / afterword(多页各有不同) / credits。"""
        last = len(self.ENDING_PAGES) - 1
        if page <= 0:
            return self.art.ending_victory
        if page >= last:
            return self.art.ending_credits
        afterword_index = page - 1
        if 0 <= afterword_index < len(self.AFTERWORD_PAGE_VISUALS):
            bg_key = self.AFTERWORD_PAGE_VISUALS[afterword_index][0]
            if bg_key == "scene":
                return self.art.scene_background
            if bg_key == "afterword":
                return self.art.ending_afterword
            if bg_key == "victory":
                return self.art.ending_victory
        return self.art.ending_afterword

    def _draw_title_screen(self) -> None:
        self.screen.blit(self.title_background, (0, 0))
        self.screen.blit(self.title_shade, (0, 0))
        title_panel = pygame.Rect(*self.TITLE_INFO_PANEL_RECT)
        self._draw_ornate_panel(title_panel)
        left = title_panel.left + 28
        self.screen.blit(
            self.font.render("红雾异变  /  STORY 01", True, config.MUTED),
            (left, title_panel.top + 28),
        )
        self.screen.blit(
            self.font_big.render("东方红雾录", True, config.PALE_GOLD),
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

        # 所有菜单项统一使用 atlas 图片风格。
        items = self._menu_items()
        count = len(items)
        btn_w, btn_h = 360, 90
        # 根据菜单项数量自适应起始位置与间距，保证全部可见。
        if count <= 4:
            start_y, gap = 500, 14
        else:
            start_y, gap = 466, 8
        for index, label in enumerate(items):
            y = start_y + index * (btn_h + gap)
            row = self.MENU_ATLAS_ROW.get(label, 0)
            selected, idle = self._menu_atlas_rows[row]
            image = selected if index == self.menu_selection else idle
            # 选中项加一层绯红高光底板，增强厚重感
            if index == self.menu_selection:
                plate = pygame.Rect(794, y - 3, btn_w + 12, btn_h + 6)
                hl = pygame.Surface(plate.size, pygame.SRCALPHA)
                hl.fill((92, 20, 34, 130))
                self.screen.blit(hl, plate.topleft)
                pygame.draw.rect(self.screen, config.GOLD, plate, 2)
            self.screen.blit(image, (800, y))

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
        if self.boss is not None and self.boss.alive:
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
        """弹幕场顶部的符卡条：符卡名、剩余段数与倒计时；无 Boss 时隐藏。"""
        boss = self.boss
        if boss is None or not boss.alive:
            return
        bar = pygame.Rect(config.PLAYFIELD_LEFT, config.PLAYFIELD_TOP,
                          config.PLAYFIELD_WIDTH, 40)
        shade = pygame.Surface(bar.size, pygame.SRCALPHA)
        shade.fill((7, 3, 9, 160))
        self.screen.blit(shade, bar.topleft)
        pygame.draw.line(
            self.screen, config.GOLD, bar.bottomleft, bar.bottomright, 1
        )

        total = boss.spell_count
        phase = min(boss.phase, total)
        self.screen.blit(
            self.font.render(boss.spell.name, True, config.PALE_GOLD),
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
        # 符卡取得数：本轮已经完整避开、未用灵击而破开的符卡张数
        captured = self.font.render(
            f"取得 {self.spells_captured}", True, config.PALE_GOLD
        )
        self.screen.blit(
            captured, captured.get_rect(midright=(bar.right - 108, bar.centery))
        )

    def _draw_spell_announcement(self) -> None:
        """符卡展开时的播报卡片：符卡名 + 技能描述，渐入渐出。"""
        boss = self.boss
        if boss is None or not boss.alive:
            return
        if self.spell_announce_timer <= 0.0:
            return
        spell = boss.spell
        if not spell.flavor and not spell.name:
            return

        field = pygame.Rect(
            config.PLAYFIELD_LEFT, config.PLAYFIELD_TOP,
            config.PLAYFIELD_WIDTH, config.PLAYFIELD_HEIGHT,
        )
        # 后 0.5 秒淡出
        total = max(0.001, config.SPELL_ANNOUNCE_DURATION)
        fade_in = min(1.0, (total - self.spell_announce_timer) / 0.3)
        fade_out = min(1.0, self.spell_announce_timer / 0.5)
        alpha = int(255 * min(fade_in, fade_out))

        card_h = 116
        card = pygame.Rect(
            field.left, field.centery - card_h // 2, field.width, card_h
        )
        shade = pygame.Surface(card.size, pygame.SRCALPHA)
        shade.fill((8, 3, 12, int(220 * min(1.0, fade_in))))
        self.screen.blit(shade, card.topleft)
        pygame.draw.line(self.screen, config.GOLD, card.topleft, card.topright, 2)
        pygame.draw.line(self.screen, config.GOLD, card.bottomleft,
                         card.bottomright, 2)

        label = self.font.render(
            f"第 {min(boss.phase, boss.spell_count)} 符卡  /  SPELL CARD",
            True, config.MUTED,
        )
        label.set_alpha(alpha)
        self.screen.blit(label, (card.left + 28, card.top + 16))

        name = self.font_big.render(spell.name, True, config.PALE_GOLD)
        name.set_alpha(alpha)
        self.screen.blit(name, (card.left + 28, card.top + 42))

        if spell.flavor:
            # 技能描述按播放场宽折成一行或两行
            flavor = spell.flavor
            max_chars = (card.width - 56) // max(1, self.font.size("字")[0])
            if len(flavor) > max_chars:
                first = flavor[:max_chars]
                second = flavor[max_chars:]
                line1 = self.font.render(first, True, config.WHITE)
                line2 = self.font.render(second, True, config.WHITE)
                line1.set_alpha(alpha)
                line2.set_alpha(alpha)
                self.screen.blit(line1, (card.left + 28, card.top + 84))
                self.screen.blit(line2, (card.left + 28, card.top + 84 + 30))
            else:
                desc = self.font.render(flavor, True, config.WHITE)
                desc.set_alpha(alpha)
                self.screen.blit(desc, (card.left + 28, card.top + 92))

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
        script = self.director.script
        stage_no = min(max(self.director.stage_number, 1), config.STAGE_COUNT)
        self.screen.blit(
            self.font_big.render(
                script.title if script is not None else "幻想郷", True,
                config.PALE_GOLD,
            ),
            (left, panel.top + 24),
        )
        self.screen.blit(
            self.font.render(
                f"STAGE {stage_no:02d}  /  {config.STAGE_COUNT}", True,
                config.MUTED,
            ),
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

        boss = self.boss
        self.screen.blit(
            self.font.render(
                boss.spec.title if boss is not None else "雜兵波次",
                True, config.PALE_GOLD,
            ),
            (left, panel.top + 218),
        )
        phase_text = self.font.render(
            f"{min(boss.phase, boss.spell_count)} / {boss.spell_count}"
            if boss is not None else "- / -",
            True, config.WHITE,
        )
        self.screen.blit(phase_text, phase_text.get_rect(topright=(right, panel.top + 218)))
        if boss is not None:
            portrait = self._boss_sprite(boss)
            self.screen.blit(portrait, portrait.get_rect(topright=(right, panel.top + 250)))

        health_ratio = max(0.0, boss.hp / boss.max_hp) if boss is not None else 0.0
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
            ("灵击  /  BOMB", self.bombs),
        )
        for index, (label, value) in enumerate(rows):
            y = panel.top + 562 + index * 32
            self.screen.blit(self.font.render(label, True, config.MUTED), (left, y))
            value_surface = self.font.render(str(value), True, config.WHITE)
            self.screen.blit(value_surface, value_surface.get_rect(topright=(right, y)))

        # 火力：标签与数值同行，进度条独占下一行（避免与标签重叠）
        power_y = panel.top + 690
        self.screen.blit(
            self.font.render("火力  /  POWER", True, config.MUTED),
            (left, power_y),
        )
        power_value = self.font.render(f"{self.power:.2f}", True, config.WHITE)
        self.screen.blit(
            power_value, power_value.get_rect(topright=(right, power_y))
        )
        power_bar = pygame.Rect(left, power_y + 30, panel.width - 48, 10)
        pygame.draw.rect(self.screen, (47, 19, 28), power_bar)
        power_fill = power_bar.inflate(-4, -4)
        power_fill.width = round(
            power_fill.width * min(1.0, self.power / config.ITEM_POWER_MAX)
        )
        if power_fill.width > 0:
            pygame.draw.rect(self.screen, config.GOLD, power_fill)
        pygame.draw.rect(self.screen, config.GOLD, power_bar, 1)

        item_y = panel.top + 736
        self.screen.blit(
            self.font.render("道具  /  ITEM", True, config.MUTED), (left, item_y)
        )
        item_value = self.font.render(str(self.item_total), True, config.WHITE)
        self.screen.blit(item_value, item_value.get_rect(topright=(right, item_y)))

        divider_y = panel.top + 766
        pygame.draw.line(
            self.screen, config.GOLD,
            (left, divider_y), (right, divider_y), 1,
        )
        self.screen.blit(
            self.font.render(
                "调  试  /  DEBUG" if self.debug_overlay else "操  作  /  CONTROL",
                True, config.PALE_GOLD,
            ),
            (left, divider_y + 16),
        )
        if self.god_mode:
            badge = pygame.Rect(right - 96, divider_y + 14, 96, 26)
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
                y = divider_y + 60 + index * 34
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
            "Shift 低速   F3 密码无敌",
            "Z 射击   X 灵击   F1 暂停",
        )
        for index, hint in enumerate(hints):
            self.screen.blit(
                self.font.render(hint, True, config.WHITE),
                (left, divider_y + 46 + index * 28),
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
