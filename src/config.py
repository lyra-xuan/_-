"""全局常量配置。

集中管理分辨率、帧率、颜色与各类实体参数，避免魔法数字散落在各处。
"""
from __future__ import annotations

# ---------- 窗口与帧率 ----------
SCREEN_W, SCREEN_H = 1280, 960
FPS = 60
# 单帧最大时间步长：卡顿/窗口拖动后 dt 会很大，夹紧可避免物体“瞬移”穿过判定区
MAX_DT = 1.0 / 30.0

# ---------- 颜色 ----------
BLACK = (8, 5, 11)
WHITE = (241, 226, 207)
RED = (204, 43, 58)
CYAN = (150, 196, 220)
YELLOW = (224, 184, 112)
GRAY = (91, 75, 76)
BLUE = (110, 150, 255)
GOLD = (187, 145, 83)
PALE_GOLD = (231, 201, 151)
PANEL = (14, 8, 15)
MUTED = (157, 133, 125)

# 弹幕配色：作为键去匹配素材贴图，与实际像素颜色无关
GREEN = (67, 255, 61)
MAGENTA = (255, 27, 254)
PURPLE = (118, 95, 255)

# ---------- 战斗区域 ----------
PLAYFIELD_LEFT = 32
PLAYFIELD_TOP = 32
PLAYFIELD_WIDTH = 768
PLAYFIELD_HEIGHT = 896
PLAYFIELD_RIGHT = PLAYFIELD_LEFT + PLAYFIELD_WIDTH
PLAYFIELD_BOTTOM = PLAYFIELD_TOP + PLAYFIELD_HEIGHT
PLAYER_START_X = PLAYFIELD_LEFT + PLAYFIELD_WIDTH / 2
PLAYER_START_Y = PLAYFIELD_BOTTOM - 120

# ---------- 玩家 ----------
PLAYER_SPEED = 560.0        # 像素/秒
PLAYER_FOCUS_FACTOR = 0.45  # 按住 Shift 低速移动时的速度系数
PLAYER_HIT_RADIUS = 4.5     # 命中判定半径（弹幕游戏惯例：极小）
PLAYER_GRAZE_RADIUS = 27.0  # 擦弹判定半径（外层）
PLAYER_START_MARGIN = 120.0
PLAYER_SPRITE_WIDTH = 46   # 素材原始 23×43，按 2 倍显示
PLAYER_SPRITE_HEIGHT = 86
PLAYER_LIVES = 3
PLAYER_INVULNERABLE_TIME = 1.5
PLAYER_SHOT_SPEED = 720.0
PLAYER_SHOT_RADIUS = 6.0
PLAYER_SHOT_DAMAGE = 10.0
PLAYER_FIRE_INTERVAL = 0.18

# ---------- 子弹 ----------
BULLET_RADIUS = 7.5
BULLET_SPEED = 225.0
BULLET_SMALL_RADIUS = 8.0
BULLET_LARGE_RADIUS = 13.0

# ---------- Boss ----------
BOSS_START_X = PLAYER_START_X
BOSS_START_Y = PLAYFIELD_TOP + 148.0
BOSS_RADIUS = 42.0
BOSS_MAX_HP = 180.0
BOSS_MOVE_SPEED = 240.0
BOSS_LEFT_BOUND = PLAYFIELD_LEFT + 128.0
BOSS_RIGHT_BOUND = PLAYFIELD_RIGHT - 128.0
BOSS_PHASE1_INTERVAL = 0.85
BOSS_PHASE2_INTERVAL = 0.60
BOSS_ATTACK_SPEED = 232.5
BOSS_FAN_COUNT = 5
BOSS_FAN_STEP_DEGREES = 12.0
BOSS_RING_COUNT = 8
BOSS_PHASE_TIME_LIMIT = 45.0  # 每个阶段的符卡限时（秒），超时强制推进下一阶段
# 各阶段的符卡名，展示在弹幕场顶部；元素数即 Boss 的总段数
BOSS_PHASE_NAMES = ("红符「猩红射击」", "红魔法「红色魔术」")

# ---------- 计分 ----------
GRAZE_SCORE = 500       # 每次擦弹
PHASE_SCORE = 5000      # 击破一个 Boss 阶段
VICTORY_SCORE = 10000   # 击破 Boss
HISCORE_FILE = "hiscore.txt"

# ---------- 特效时长（秒） ----------
HIT_SPARK_DURATION = 0.20
GRAZE_RING_DURATION = 0.28
BURST_DURATION = 0.60
BOSS_FLASH_DURATION = 0.16

# ---------- 弹幕场暗角 ----------
VIGNETTE_COLOR = (10, 3, 9)
VIGNETTE_MAX_ALPHA = 205

# ---------- 装饰妖精 ----------
FAIRY_SPAWN_MIN = 1.1      # 两次生成之间的最短间隔（秒）
FAIRY_SPAWN_MAX = 2.4
FAIRY_SPEED_MIN = 40.0     # 下落速度范围（像素/秒）
FAIRY_SPEED_MAX = 78.0
FAIRY_SWAY_MIN = 18.0      # 左右摆动幅度范围（像素/秒）
FAIRY_SWAY_MAX = 46.0

# ---------- 空间网格 ----------
GRID_CELL_SIZE = 96

# ---------- 碰撞调试可视化 ----------
DEBUG_OVERLAY_DEFAULT = False   # 启动时是否直接显示调试层
DEBUG_GRID_COLOR = (62, 78, 96)
DEBUG_GRID_ALPHA = 80
DEBUG_HIT_COLOR = (255, 92, 92)      # 命中区（内层，致命）
DEBUG_GRAZE_COLOR = (120, 196, 255)  # 擦弹区（外层，不致命）
DEBUG_SWEEP_COLOR = (255, 198, 104)  # 本帧扫掠线段
