"""全局常量配置。

集中管理分辨率、帧率、颜色与各类实体参数，避免魔法数字散落在各处。
"""
from __future__ import annotations

# ---------- 窗口与帧率 ----------
SCREEN_W, SCREEN_H = 480, 640
FPS = 60
# 单帧最大时间步长：卡顿/窗口拖动后 dt 会很大，夹紧可避免物体“瞬移”穿过判定区
MAX_DT = 1.0 / 30.0

# ---------- 颜色 ----------
BLACK = (10, 10, 18)
WHITE = (240, 240, 245)
RED = (235, 70, 80)
CYAN = (90, 220, 255)
YELLOW = (250, 220, 90)
GRAY = (100, 100, 120)
BLUE = (110, 150, 255)

# ---------- 玩家 ----------
PLAYER_SPEED = 280.0        # 像素/秒
PLAYER_FOCUS_FACTOR = 0.45  # 按住 Shift 低速移动时的速度系数
PLAYER_HIT_RADIUS = 3.0     # 命中判定半径（弹幕游戏惯例：极小）
PLAYER_GRAZE_RADIUS = 18.0  # 擦弹判定半径（外层）
PLAYER_SHOT_SPEED = 480.0
PLAYER_SHOT_RADIUS = 4.0
PLAYER_SHOT_DAMAGE = 10.0
PLAYER_FIRE_INTERVAL = 0.18

# ---------- 子弹 ----------
BULLET_RADIUS = 5.0
BULLET_SPEED = 150.0

# ---------- Boss ----------
BOSS_START_Y = 92.0
BOSS_RADIUS = 28.0
BOSS_MAX_HP = 180.0
BOSS_MOVE_SPEED = 90.0
BOSS_LEFT_BOUND = 64.0
BOSS_RIGHT_BOUND = SCREEN_W - 64.0
BOSS_PHASE1_INTERVAL = 0.85
BOSS_PHASE2_INTERVAL = 0.60
BOSS_ATTACK_SPEED = 155.0
BOSS_FAN_COUNT = 5
BOSS_FAN_STEP_DEGREES = 12.0
BOSS_RING_COUNT = 8

# ---------- 空间网格 ----------
GRID_CELL_SIZE = 64
