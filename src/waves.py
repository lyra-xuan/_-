"""波次编队：把一条「波次脚本」展开成具体的杂兵实例。

这里只做纯计算（坐标、出场时间、实体构造），不接触屏幕与主循环，方便单独
测试；真正的计时与投放由 :class:`src.director.StageDirector` 负责。

``formation`` 描述编队的空间形状，同一条波次里的杂兵共享弹型与运动参数，
只是横向位置和出场时间不同——这正是原作里「一排妖精横着压下来」的观感。
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config
from .entities import Fairy
from .spells import Emitter

# 编队可用横向范围：两端各留出一点，免得贴边生成
_LEFT = config.PLAYFIELD_LEFT + 56.0
_RIGHT = config.PLAYFIELD_RIGHT - 56.0
_ENTRY_Y = config.PLAYFIELD_TOP - config.WAVE_ENTRY_MARGIN


@dataclass(frozen=True)
class WaveSpec:
    """一条波次：编队形状 + 共享的杂兵参数。"""

    formation: str = "line"       # line / arc / vee / column / sides / chase
    count: int = 6
    frames: str = "small1"        # art.enemy_frames 的键
    speed: float = 68.0
    sway: float = 24.0
    hp: float = config.FAIRY_HP
    drop: str | None = None       # 指定掉落种类；为空时走全局轮换表
    attack: Emitter | None = None
    hover_y: float | None = None
    hover_time: float = 0.0
    delay: float = 0.0            # 本条波次相对上一波的等待时间
    spread: float = 0.0           # 编队内各机的出场时间差


def _even_ratio(index: int, count: int) -> float:
    """把第 ``index`` 台均匀铺到 0~1 的横向比例上。"""
    if count <= 1:
        return 0.5
    return index / (count - 1)


def _layout(formation: str, count: int) -> list[tuple[float, float]]:
    """返回每台杂兵的 ``(横向比例, 出场延迟系数)``。"""
    middle = (count - 1) / 2.0
    spread_from_middle = (
        abs(index - middle) / middle if middle > 0.0 else 0.0
        for index in range(count)
    )
    if formation == "arc":
        # 中间先落、两翼随后压上，形成一道弧
        return [(_even_ratio(i, count), value)
                for i, value in enumerate(spread_from_middle)]
    if formation == "vee":
        # 两翼先入场、中间殿后，像自两侧收拢的雁阵
        return [(_even_ratio(i, count), 1.0 - value)
                for i, value in enumerate(spread_from_middle)]
    if formation == "column":
        # 同一竖直通道鱼贯而下
        return [(0.5, float(i)) for i in range(count)]
    if formation == "sides":
        # 左右边缘交替进场
        return [(0.07 if i % 2 == 0 else 0.93, float(i // 2))
                for i in range(count)]
    if formation == "chase":
        # 三条通道交错跟进，制造追击感
        return [(0.16 + 0.34 * (i % 3), 0.6 * i) for i in range(count)]
    # line：一字横排、同时入场
    return [(_even_ratio(i, count), 0.0) for i in range(count)]


def build_wave(spec: WaveSpec) -> tuple[tuple[float, Fairy], ...]:
    """展开成 ``(出场延迟, 杂兵)`` 列表，延迟以波次起点为基准。"""
    span = _RIGHT - _LEFT
    enemies = []
    for ratio, delay_factor in _layout(spec.formation, spec.count):
        enemies.append((
            spec.delay + spec.spread * delay_factor,
            Fairy(
                _LEFT + span * ratio, _ENTRY_Y, spec.speed, spec.sway,
                frames_key=spec.frames, hp=spec.hp, drop=spec.drop,
                attack=spec.attack, hover_y=spec.hover_y,
                hover_time=spec.hover_time,
            ),
        ))
    return tuple(enemies)


def wave_duration(spec: WaveSpec) -> float:
    """本条波次最后一台杂兵的出场时间。"""
    return max((delay for delay, _ in build_wave(spec)), default=0.0)
