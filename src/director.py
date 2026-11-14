"""关卡推进编排：逐条执行 ``StageScript.steps()``。

``game.py`` 原本只认识「一个 Boss」，这里把关卡脚本变成一条可推进的状态序列——
过场 → 对话 → 杂兵波次 → 中 Boss → 关底 Boss → 结算——由本类决定「什么时候该
做什么」，``Game`` 只负责响应：投放 ``update`` 返回的杂兵、按需取自
``take_boss`` 生成 Boss、在 Boss 被击破时回报，以及把当前状态画出来。

本类不持有任何 pygame 资源，也不关心渲染，因此可以脱离窗口单独测试。
"""
from __future__ import annotations

from . import config
from .dialogue import DialogueBox
from .entities import Fairy
from .spells import BossSpec
from .stages import STAGES, Banner, Clear, Fight, StageScript, Talk, Waves
from .waves import build_wave, wave_duration

# 步骤类型即状态；DONE 表示三关全部结束
BANNER = "banner"
TALK = "talk"
WAVES = "waves"
FIGHT = "fight"
CLEAR = "clear"
DONE = "done"


class StageDirector:
    """把关卡脚本走成一条时间线。"""

    def __init__(self, stages: tuple[StageScript, ...] = STAGES,
                 start_stage: int = 0) -> None:
        self.stages = tuple(stages)
        self.start_stage = start_stage      # 从哪一关开始（0 起）
        self.stage_number = 0               # 1 起的当前关卡序号
        self.script: StageScript | None = None
        self.steps: tuple = ()
        self.step_index = 0
        self.state = DONE
        self.timer = 0.0                    # 当前步骤已停留的时间
        self.dialogue: DialogueBox | None = None
        self.pending_boss: BossSpec | None = None
        self.cleared_stage = 0              # 最近一次结算的关卡序号
        self.completed = False
        self.started = False
        self._queue: list[tuple[float, Fairy]] = []
        self._elapsed = 0.0
        self._boss_defeated = False

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    @property
    def step(self):
        """当前步骤对象；越界时为 ``None``。"""
        if 0 <= self.step_index < len(self.steps):
            return self.steps[self.step_index]
        return None

    @property
    def banner(self) -> Banner | None:
        return self.step if self.state == BANNER else None

    @property
    def waiting_dialogue(self) -> bool:
        """是否正等待玩家推进对话。"""
        return self.state == TALK and self.dialogue is not None

    @property
    def in_fight(self) -> bool:
        return self.state == FIGHT

    @property
    def background_index(self) -> int:
        return self.script.background if self.script is not None else 0

    # ------------------------------------------------------------------ #
    # 控制
    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        """回到指定起始关卡开头。"""
        self.__init__(self.stages, self.start_stage)

    def start(self) -> None:
        if self.started or not self.stages:
            return
        self.started = True
        self._enter_stage(self.start_stage)

    def take_boss(self) -> BossSpec | None:
        """取走待出场的 Boss（只取一次），供 ``Game`` 生成实例。"""
        spec = self.pending_boss
        self.pending_boss = None
        return spec

    def notify_boss_defeated(self) -> None:
        self._boss_defeated = True

    def advance_dialogue(self) -> bool:
        """推进一句台词；返回 ``True`` 表示整场对话已经结束。"""
        if self.dialogue is None:
            return True
        if self.dialogue.advance():
            self._next()
            return True
        return False

    # ------------------------------------------------------------------ #
    # 推进
    # ------------------------------------------------------------------ #
    def update(self, dt: float,
               alive_fairies: int = 0) -> tuple[Fairy, ...]:
        """推进当前步骤，返回本帧应当投放的杂兵。"""
        if not self.started or self.state == DONE:
            return ()

        if self.state == BANNER:
            self.timer += dt
            if self.timer >= self.step.duration:
                self._next()
            return ()

        if self.state == TALK:
            if self.dialogue is not None:
                self.dialogue.update(dt)
            return ()

        if self.state == WAVES:
            return self._update_waves(dt, alive_fairies)

        if self.state == FIGHT:
            # 待出场的 Boss 已被取走，且已回报击破，则本场结束
            if self.pending_boss is None and self._boss_defeated:
                self._next()
            return ()

        if self.state == CLEAR:
            self.timer += dt
            if self.timer >= self.step.duration:
                self._next()
        return ()

    def _update_waves(self, dt: float,
                      alive_fairies: int) -> tuple[Fairy, ...]:
        self._elapsed += dt
        spawned: list[Fairy] = []
        waiting: list[tuple[float, Fairy]] = []
        for delay, fairy in self._queue:
            if delay <= self._elapsed:
                spawned.append(fairy)
            else:
                waiting.append((delay, fairy))
        self._queue = waiting
        # 本帧投放后场上还有杂兵（``alive_fairies`` 是本帧投放前的人数）就继续等，
        # 免得最后一台刚入场就被判为「已清空」而提前进入下一段。
        if not self._queue and alive_fairies + len(spawned) == 0:
            self._next()
        return tuple(spawned)

    # ------------------------------------------------------------------ #
    # 步骤切换
    # ------------------------------------------------------------------ #
    def _enter_stage(self, index: int) -> None:
        self.script = self.stages[index]
        self.stage_number = index + 1
        self.steps = self.script.steps()
        self.step_index = 0
        self._enter()

    def _next(self) -> None:
        self.step_index += 1
        self._enter()

    def _enter(self) -> None:
        step = self.step
        self.timer = 0.0
        self.dialogue = None
        self._queue = []
        self._elapsed = 0.0

        if step is None:
            # 本关步骤走完：单关模式下直接结束整局（关卡选择界面负责解锁下一关）
            self.state = DONE
            self.completed = True
            return

        if isinstance(step, Banner):
            self.state = BANNER
        elif isinstance(step, Talk):
            self.state = TALK
            self.dialogue = DialogueBox(step.scene)
        elif isinstance(step, Waves):
            self.state = WAVES
            self._queue = self._build_queue(step)
        elif isinstance(step, Fight):
            self.state = FIGHT
            self.pending_boss = step.spec
            self._boss_defeated = False
        elif isinstance(step, Clear):
            self.state = CLEAR
            self.cleared_stage = step.stage_index

    @staticmethod
    def _build_queue(step: Waves) -> list[tuple[float, Fairy]]:
        """把多条波次摊平成一条按出场时间排序的队列。

        每条波次在上一条结束（最后一台入场）后再等 ``WAVE_LULL`` 才铺开，
        于是杂兵呈连绵之势而非同时涌出。
        """
        queue: list[tuple[float, Fairy]] = []
        offset = 0.0
        for spec in step.waves:
            for delay, fairy in build_wave(spec):
                queue.append((offset + delay, fairy))
            offset += wave_duration(spec) + config.WAVE_LULL
        queue.sort(key=lambda entry: entry[0])
        return queue
