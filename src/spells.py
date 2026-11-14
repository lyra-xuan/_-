"""数据驱动的弹幕发射器与符卡。

原本 ``game.py`` 里的「阶段 1 / 2 / 3」分支是硬编码的，加一张符卡就要多写
一个 ``if``。这里把弹幕拆成两层：

* :class:`Emitter` —— 一次发射的形状（扇形 / 环形 / 螺旋 / 散射），只描述
  角度与速度，由 :func:`emit` 统一展开成 :class:`~src.entities.Bullet`；
* :class:`SpellCard` / :class:`BossSpec` —— 一张符卡含若干发射器，一个 Boss
  含若干符卡。

于是「三关十余名角色、每人一到五张符卡」只是数据，运行时代码不需要认识任何
一个具体角色。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

from . import config
from .entities import Bullet

# 弹型键写作 ``尺寸_颜色``，尺寸决定判定半径与贴图集，颜色只用于无贴图时回退
_BULLET_RADII = {
    "small": config.BULLET_SMALL_RADIUS,
    "mid": config.BULLET_MID_RADIUS,
    "large": config.BULLET_LARGE_RADIUS,
}
_BULLET_TINTS = {
    "white": config.WHITE,
    "red": config.RED,
    "green": config.GREEN,
    "blue": config.BLUE,
    "cyan": config.CYAN,
    "magenta": config.MAGENTA,
    "purple": config.PURPLE,
    "yellow": config.YELLOW,
    "gray": config.GRAY,
}


@dataclass(frozen=True)
class Emitter:
    """一次发射的形状描述。

    ``kind`` 取 ``fan`` / ``ring`` / ``spiral`` / ``scatter``；``ring`` 与
    ``spiral`` 的区别只在于调用方是否把 ``angle`` 相位逐次累加 ``spin``。
    """

    kind: str = "fan"
    interval: float = 0.85
    count: int = 5
    step: float = 12.0          # 相邻弹的角度间隔（度）
    speed: float = 232.5
    speed_max: float = 0.0      # 仅 scatter 使用，构成速度区间
    spin: float = 0.0           # 每次发射整体旋转的角度（度），供 ring / spiral
    bullet: str = "small_red"
    aim: bool = False           # 是否以自机方向作为基准角
    offset: float = 0.0         # 基准角度偏移（度）


@dataclass(frozen=True)
class SpellCard:
    """一张符卡：一组同时生效的发射器，加生命值与限时。"""

    name: str
    emitters: tuple[Emitter, ...]
    hp: float = 180.0
    duration: float = config.BOSS_PHASE_TIME_LIMIT
    flavor: str = ""          # 符卡展开时的风格化描述（贴近原作的技能解说）

    def cooldowns(self) -> list[float]:
        """各发射器的初始计时器，首个发射器立即开火。"""
        return [0.0] + [e.interval for e in self.emitters[1:]]


@dataclass(frozen=True)
class BossSpec:
    """一个可战斗角色的完整规格：立绘键、显示名与符卡列表。"""

    key: str
    title: str
    spells: tuple[SpellCard, ...]
    midboss: bool = False

    @property
    def max_hp(self) -> float:
        return sum(spell.hp for spell in self.spells)


def bullet_sprite(art, key: str) -> pygame.Surface | None:
    """按 ``尺寸_颜色`` 取贴图；取不到时返回 ``None``，交由 Bullet 画圆。"""
    size, _, color = key.partition("_")
    table = {
        "small": getattr(art, "bullet_small", {}),
        "mid": getattr(art, "bullet_mid", {}),
        "large": getattr(art, "bullet_large", {}),
    }.get(size)
    if not table:
        return None
    return table.get(color)


def bullet_profile(key: str) -> tuple[float, tuple[int, int, int]]:
    """由弹型键推出判定半径与回退颜色。"""
    size, _, color = key.partition("_")
    return (
        _BULLET_RADII.get(size, config.BULLET_SMALL_RADIUS),
        _BULLET_TINTS.get(color, config.RED),
    )


def _bullet(origin, angle: float, speed: float, radius: float, color, sprite,
            ) -> Bullet:
    return Bullet(
        origin.x, origin.y,
        math.cos(angle) * speed, math.sin(angle) * speed,
        radius=radius, color=color, sprite=sprite,
    )


def emit(emitter: Emitter, art, origin, aim_point, angle: float = 0.0,
         ) -> list[Bullet]:
    """把一次发射展开成子弹列表。

    ``angle`` 是整体相位（弧度），``ring`` / ``spiral`` 会叠加在它之上；
    ``aim_point`` 只在 ``emitter.aim`` 为真时参与计算。
    """
    radius, color = bullet_profile(emitter.bullet)
    sprite = bullet_sprite(art, emitter.bullet)
    origin = origin
    base = 0.0
    if emitter.aim:
        delta = aim_point - origin
        base = math.atan2(delta.y, delta.x) if delta.length_squared() else math.pi / 2

    if emitter.kind == "scatter":
        high = max(emitter.speed, emitter.speed_max)
        return [
            _bullet(origin, random.uniform(0.0, math.tau),
                    random.uniform(emitter.speed, high), radius, color, sprite)
            for _ in range(emitter.count)
        ]

    if emitter.kind == "fan":
        middle = (emitter.count - 1) / 2.0
        return [
            _bullet(origin,
                    base + math.radians(emitter.offset + (i - middle) * emitter.step),
                    emitter.speed, radius, color, sprite)
            for i in range(emitter.count)
        ]

    # ring / spiral：整圈均分，叠加相位
    count = max(1, emitter.count)
    return [
        _bullet(origin,
                math.radians(emitter.offset) + angle + math.tau * i / count,
                emitter.speed, radius, color, sprite)
        for i in range(count)
    ]


# --------------------------------------------------------------------------- #
# 符卡与 Boss 规格
# --------------------------------------------------------------------------- #
# 符卡名沿用原作红魔乡的日文命名，弹幕式样按可玩性重新编排。
# 中 Boss 用一张低血量短符卡做「预演」，关底 Boss 用多张构成完整战斗。

_MID_DURATION = 20.0
_BOSS_DURATION = 40.0


def _spell(name: str, hp: float, duration: float, *emitters: Emitter,
           flavor: str = "") -> SpellCard:
    return SpellCard(name=name, emitters=emitters, hp=hp, duration=duration,
                     flavor=flavor)


DEFAULT_BOSS_SPEC = BossSpec(
    key="remilia",
    title="蕾米莉亚·史卡雷特",
    spells=(
        _spell("红符「猩红射击」", 180.0, _BOSS_DURATION,
               Emitter(kind="fan", interval=0.70, count=5, step=12.0,
                       speed=232.5, bullet="small_red", aim=True),
               Emitter(kind="ring", interval=1.45, count=10, speed=170.0,
                       spin=9.0, bullet="small_blue"),
               flavor="以猩红之弹直指巫女，再以蓝弹之环封锁退路。"),
        _spell("红魔法「红色魔术」", 180.0, _BOSS_DURATION,
               Emitter(kind="ring", interval=1.10, count=8, speed=225.0,
                       bullet="large_magenta"),
               Emitter(kind="ring", interval=1.10, count=16, offset=180.0 / 16,
                       speed=162.0, bullet="small_white"),
               flavor="大小双层弹环交错旋转，将战场染成一片赤红。"),
        _spell("神枪「冈格尼尔之枪」", 180.0, _BOSS_DURATION,
               Emitter(kind="spiral", interval=0.13, count=6, speed=232.5,
                       spin=17.0, bullet="small_blue"),
               Emitter(kind="scatter", interval=0.60, count=4, speed=120.0,
                       speed_max=240.0, bullet="large_magenta"),
               flavor="命运之枪螺旋贯穿，再以散弹碎裂一切躲避的余地。"),
    ),
)


MIDBOSS_SPECS = {
    "rumia": BossSpec(
        key="rumia", title="露米娅", midboss=True,
        spells=(
            _spell("闇符「黑暗侧之月」", config.MIDBOSS_HP, _MID_DURATION,
                   Emitter(kind="fan", interval=0.95, count=5, step=11.0,
                           speed=215.0, bullet="small_red", aim=True),
                   Emitter(kind="ring", interval=1.70, count=8, speed=150.0,
                           offset=22.5, bullet="large_purple"),
                   flavor="黑暗中潜伏的红弹瞄准要害，紫弹之环缓缓合围。"),
        ),
    ),
    "cirno": BossSpec(
        key="cirno", title="琪露诺", midboss=True,
        spells=(
            _spell("冰符「冰柱坠落」", config.MIDBOSS_HP, _MID_DURATION,
                   Emitter(kind="fan", interval=0.85, count=7, step=14.0,
                           speed=200.0, bullet="large_cyan", aim=True),
                   Emitter(kind="ring", interval=1.30, count=6, speed=165.0,
                           spin=-13.0, bullet="small_white"),
                   flavor="巨大冰柱自天而降，碎冰之环逆时针封死全场。"),
        ),
    ),
    "meiling": BossSpec(
        key="meiling", title="红美铃", midboss=True,
        spells=(
            _spell("华符「芳华绚烂」", config.MIDBOSS_HP, _MID_DURATION,
                   Emitter(kind="spiral", interval=0.22, count=5, speed=190.0,
                           spin=23.0, bullet="mid_red"),
                   Emitter(kind="fan", interval=1.20, count=3, step=16.0,
                           speed=240.0, bullet="small_green", aim=True),
                   flavor="拳法螺旋连发，间杂瞄准的绿弹，攻防一体的门卫式。"),
        ),
    ),
    "patchouli": BossSpec(
        key="patchouli", title="帕秋莉·诺蕾姬", midboss=True,
        spells=(
            _spell("火符「阿耆尼之辉」", config.MIDBOSS_HP, _MID_DURATION,
                   Emitter(kind="ring", interval=0.95, count=12, speed=185.0,
                           spin=7.0, bullet="small_red"),
                   Emitter(kind="fan", interval=1.40, count=5, step=9.0,
                           speed=230.0, bullet="large_yellow", aim=True),
                   flavor="火炎之环缓缓旋转，黄焰巨弹直指闯入者的眉心。"),
        ),
    ),
    "sakuya": BossSpec(
        key="sakuya", title="十六夜咲夜", midboss=True,
        spells=(
            _spell("奇术「误导」", config.MIDBOSS_HP, _MID_DURATION,
                   Emitter(kind="fan", interval=0.55, count=9, step=8.0,
                           speed=250.0, bullet="mid_white", aim=True),
                   Emitter(kind="scatter", interval=0.90, count=5, speed=130.0,
                           speed_max=230.0, bullet="small_blue"),
                   flavor="飞刀齐射扰乱视线，再以散弹制造时间错位的错觉。"),
        ),
    ),
}


STAGE_BOSS_SPECS = {
    "rumia": BossSpec(
        key="rumia", title="露米娅",
        spells=(
            _spell("闇符「黑暗侧之月」", 180.0, _BOSS_DURATION,
                   Emitter(kind="ring", interval=1.00, count=10, speed=205.0,
                           spin=8.0, bullet="small_white"),
                   Emitter(kind="fan", interval=1.55, count=6, step=13.0,
                           speed=245.0, bullet="small_red", aim=True),
                   flavor="白弹之环缓缓旋转，红弹扇形自暗处直取性命。"),
            _spell("夜符「夜雀」", 180.0, _BOSS_DURATION,
                   Emitter(kind="spiral", interval=0.16, count=4, speed=215.0,
                           spin=19.0, bullet="large_purple"),
                   Emitter(kind="scatter", interval=0.75, count=5, speed=140.0,
                           speed_max=250.0, bullet="small_blue"),
                   flavor="紫弹螺旋如夜雀振翅，蓝弹四散扰乱听觉。"),
            _spell("闇符「分界」", 180.0, _BOSS_DURATION,
                   Emitter(kind="ring", interval=0.85, count=18, speed=175.0,
                           spin=-11.0, bullet="small_gray"),
                   Emitter(kind="fan", interval=0.50, count=3, step=22.0,
                           speed=270.0, bullet="mid_red", aim=True),
                   flavor="灰弹密环划分生死之界，红弹三连射贯穿分界。"),
        ),
    ),
    "cirno": BossSpec(
        key="cirno", title="琪露诺",
        spells=(
            _spell("冰符「冰柱坠落」", 180.0, _BOSS_DURATION,
                   Emitter(kind="fan", interval=0.62, count=7, step=13.0,
                           speed=235.0, bullet="large_cyan", aim=True),
                   Emitter(kind="ring", interval=1.35, count=8, speed=160.0,
                           spin=-9.0, bullet="small_white"),
                   flavor="巨大冰柱扇形坠下，白冰之环逆时针封锁全场。"),
            _spell("雹符「冰雹风暴」", 180.0, _BOSS_DURATION,
                   Emitter(kind="scatter", interval=0.30, count=6, speed=110.0,
                           speed_max=260.0, bullet="small_blue"),
                   Emitter(kind="ring", interval=1.80, count=12, speed=140.0,
                           spin=6.0, bullet="mid_white"),
                   flavor="冰雹暴风肆虐，蓝白乱弹交织成冰之牢笼。"),
            _spell("雪符「钻石暴风雪」", 180.0, _BOSS_DURATION,
                   Emitter(kind="spiral", interval=0.12, count=6, speed=225.0,
                           spin=-21.0, bullet="small_white"),
                   Emitter(kind="ring", interval=1.60, count=6, speed=130.0,
                           spin=9.0, bullet="large_cyan"),
                   flavor="雪之螺旋逆卷全场，冰钻之环奏响最强的音色。"),
        ),
    ),
    "remilia": BossSpec(
        key="remilia", title="蕾米莉亚·史卡雷特",
        spells=(
            _spell("红符「猩红射击」", 320.0, _BOSS_DURATION,
                   Emitter(kind="fan", interval=0.55, count=9, step=10.0,
                           speed=255.0, bullet="small_red", aim=True),
                   Emitter(kind="ring", interval=1.30, count=14, speed=175.0,
                           spin=10.0, bullet="small_blue"),
                   flavor="猩红弹幕直指巫女，蓝弹之环封住一切退路。"),
            _spell("红魔法「红色魔术」", 360.0, _BOSS_DURATION,
                   Emitter(kind="ring", interval=0.80, count=12, speed=215.0,
                           bullet="large_magenta"),
                   Emitter(kind="ring", interval=0.80, count=20, offset=180.0 / 20,
                           speed=155.0, bullet="small_white"),
                   Emitter(kind="fan", interval=1.50, count=5, step=14.0,
                           speed=270.0, bullet="mid_red", aim=True),
                   flavor="大小双层魔弹交错，红弹扇形点缀其间。"),
            _spell("冥符「红色的冥界」", 400.0, _BOSS_DURATION,
                   Emitter(kind="spiral", interval=0.09, count=6, speed=225.0,
                           spin=15.0, bullet="small_purple"),
                   Emitter(kind="scatter", interval=0.65, count=8, speed=140.0,
                           speed_max=290.0, bullet="large_magenta"),
                   Emitter(kind="ring", interval=1.80, count=16, speed=190.0,
                           spin=-8.0, bullet="small_red"),
                   flavor="冥界紫弹螺旋不绝，红弹之环倒卷而回。"),
            _spell("神罚「年幼的恶魔之王」", 440.0, _BOSS_DURATION,
                   Emitter(kind="spiral", interval=0.07, count=8, speed=240.0,
                           spin=12.0, bullet="small_purple"),
                   Emitter(kind="fan", interval=0.85, count=7, step=13.0,
                           speed=275.0, bullet="mid_red", aim=True),
                   Emitter(kind="ring", interval=1.20, count=10, speed=200.0,
                           spin=16.0, bullet="large_cyan"),
                   flavor="王罚之螺旋覆盖天际，红弹与冰环交错降下神罚。"),
            _spell("神枪「冈格尼尔之枪」", 480.0, _BOSS_DURATION,
                   Emitter(kind="fan", interval=0.15, count=5, step=4.0,
                           speed=340.0, bullet="large_cyan", aim=True),
                   Emitter(kind="ring", interval=1.05, count=12, speed=185.0,
                           spin=-15.0, bullet="small_red"),
                   Emitter(kind="spiral", interval=0.11, count=4, speed=260.0,
                           spin=21.0, bullet="mid_white"),
                   flavor="命运之枪以极高射速贯穿，红环白螺旋交织成终局。"),
        ),
    ),
}
