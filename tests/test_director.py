"""关卡编排（StageDirector）的状态机测试。

关卡流程不再由 ``Game`` 里的计时器决定，而是由 ``StageDirector`` 把剧本走成
「过场 → 对话 → 波次 → 中 Boss → 关底 Boss → 结算」的序列。这里用一份最小的
两关剧本独立验证这条时间线，不涉及任何 pygame 资源。
"""
import unittest

from src import config
from src.dialogue import Line, Scene
from src.director import (
    BANNER, CLEAR, DONE, FIGHT, TALK, WAVES, StageDirector,
)
from src.spells import BossSpec, Emitter, SpellCard
from src.stages import Clear, StageScript
from src.waves import WaveSpec


def make_spec(key: str) -> BossSpec:
    """一张符卡的最小 Boss 规格。"""
    return BossSpec(
        key=key,
        title=f"{key} · 测试",
        spells=(SpellCard(name="测试符", emitters=(Emitter(),),
                          hp=100.0, duration=5.0),),
    )


def make_script(index: int, midboss: bool = True) -> StageScript:
    """一关的最小剧本：开场白 → 一波杂兵 →（中 Boss）→ 关底 Boss → 结算。"""
    return StageScript(
        index=index,
        title=f"Stage {index}",
        subtitle=f"sub {index}",
        background=index - 1,
        enemy_small="small1",
        enemy_large="large1",
        waves=(WaveSpec(formation="line", count=2, speed=60.0, sway=0.0),),
        boss=make_spec(f"boss{index}"),
        midboss=make_spec(f"mid{index}") if midboss else None,
        intro=Scene(title="intro", lines=(Line("reimu", "开场", 0),)),
        boss_pre=Scene(title="pre", lines=(Line("reimu", "遭遇", 0),)),
    )


class DirectorFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scripts = (make_script(1), make_script(2))
        self.director = StageDirector(self.scripts)

    def pump(self, times: int = 1) -> None:
        """推进 ``times`` 步，自动处理对话翻页与 Boss 击破回报。"""
        for _ in range(times):
            state = self.director.state
            step = self.director.step
            if self.director.waiting_dialogue:
                self.director.advance_dialogue()
            elif state in (BANNER, CLEAR) and step is not None:
                self.director.update(step.duration + 0.01)
            elif state == FIGHT:
                self.director.take_boss()
                self.director.notify_boss_defeated()
                self.director.update(0.0)
            elif state == WAVES:
                # 第一帧投放、第二帧场上已清空，波次才会放行
                self.director.update(1.0, alive_fairies=0)
                self.director.update(1.0, alive_fairies=0)
            else:
                self.director.update(0.0)

    # ------------------------------------------------------------------ #
    # 起步与过场
    # ------------------------------------------------------------------ #
    def test_start_enters_the_first_banner(self) -> None:
        self.director.start()

        self.assertEqual(self.director.state, BANNER)
        self.assertEqual(self.director.stage_number, 1)
        self.assertIsNotNone(self.director.banner)
        self.assertEqual(self.director.background_index, 0)

    def test_start_is_idempotent(self) -> None:
        self.director.start()
        self.director.update(config.STAGE_BANNER_DURATION)
        self.director.start()

        self.assertEqual(self.director.state, TALK)

    def test_unstarted_director_does_nothing(self) -> None:
        self.assertEqual(self.director.state, DONE)
        self.assertEqual(self.director.update(1.0), ())
        self.assertIsNone(self.director.take_boss())

    def test_banner_holds_then_advances_to_dialogue(self) -> None:
        self.director.start()

        self.director.update(config.STAGE_BANNER_DURATION - 0.1)
        self.assertEqual(self.director.state, BANNER)

        self.director.update(0.2)
        self.assertEqual(self.director.state, TALK)
        self.assertTrue(self.director.waiting_dialogue)

    # ------------------------------------------------------------------ #
    # 对话
    # ------------------------------------------------------------------ #
    def test_dialogue_reveals_over_time_and_pauses_the_timeline(self) -> None:
        self.director.start()
        self.director.update(config.STAGE_BANNER_DURATION)

        line = self.director.dialogue.line
        self.assertIsNotNone(line)
        self.assertFalse(self.director.dialogue.reveal)

        # 对话中 update 只推进打字机，不换步骤
        self.director.update(10.0)
        self.assertEqual(self.director.state, TALK)
        self.assertTrue(self.director.dialogue.reveal)

    def test_first_advance_completes_the_line_and_second_ends_the_scene(self) -> None:
        self.director.start()
        self.director.update(config.STAGE_BANNER_DURATION)

        self.assertFalse(self.director.advance_dialogue())   # 先补全本行
        self.assertTrue(self.director.advance_dialogue())    # 整场结束
        self.assertEqual(self.director.state, WAVES)
        self.assertFalse(self.director.waiting_dialogue)

    # ------------------------------------------------------------------ #
    # 波次
    # ------------------------------------------------------------------ #
    def test_waves_release_fairies_and_wait_until_the_field_is_clear(self) -> None:
        self.director.start()
        self.pump(3)                       # 过场 → 对话 → 波次
        self.assertEqual(self.director.state, WAVES)

        spawned = self.director.update(0.0)
        self.assertEqual(len(spawned), 2)
        self.assertEqual(spawned[0].frames_key, "small1")

        # 场上仍有杂兵时不得推进
        self.director.update(0.1, alive_fairies=len(spawned))
        self.assertEqual(self.director.state, WAVES)

        # 清空后才进入下一段（中 Boss）
        self.director.update(0.1, alive_fairies=0)
        self.assertEqual(self.director.state, FIGHT)

    # ------------------------------------------------------------------ #
    # Boss 战
    # ------------------------------------------------------------------ #
    def test_fight_yields_its_boss_exactly_once(self) -> None:
        self.director.start()
        self.pump(4)                       # 过场 → 对话 → 波次 → 中 Boss
        self.assertEqual(self.director.state, FIGHT)
        self.assertTrue(self.director.in_fight)

        first = self.director.take_boss()
        self.assertIsNotNone(first)
        self.assertIsNone(self.director.take_boss())

    def test_fight_ends_only_after_the_boss_is_reported_defeated(self) -> None:
        self.director.start()
        self.pump(4)
        self.director.take_boss()

        self.director.update(1.0)
        self.assertEqual(self.director.state, FIGHT)

        self.director.notify_boss_defeated()
        self.director.update(0.0)
        self.assertEqual(self.director.state, TALK)   # 关底前的对峙

    def test_midboss_and_final_boss_are_different_specs(self) -> None:
        self.director.start()
        self.pump(4)
        midboss = self.director.take_boss()
        self.director.notify_boss_defeated()
        self.director.update(0.0)
        self.pump(2)                                   # 对峙对话
        self.assertEqual(self.director.state, FIGHT)
        final = self.director.take_boss()

        self.assertIsNotNone(midboss)
        self.assertIsNotNone(final)
        self.assertNotEqual(midboss.key, final.key)

    # ------------------------------------------------------------------ #
    # 结算、推进与整局
    # ------------------------------------------------------------------ #
    def test_clear_step_marks_the_finished_stage(self) -> None:
        self.director.start()
        step_index = next(
            index for index, step in enumerate(self.director.steps)
            if isinstance(step, Clear)
        )
        self.director.step_index = step_index
        self.director._enter()

        self.assertEqual(self.director.state, CLEAR)
        self.assertEqual(self.director.cleared_stage, 1)

    def test_stage_clear_ends_the_run_in_done_state(self) -> None:
        """单关模式：走完一关即结束整局，由关卡选择界面负责解锁下一关。"""
        self.director.start()
        self.pump(9)                       # 刚好走完第一关

        self.assertEqual(self.director.state, DONE)
        self.assertTrue(self.director.completed)
        self.assertEqual(self.director.cleared_stage, 1)
        self.assertEqual(self.director.stage_number, 1)

    def test_run_ends_completed_regardless_of_remaining_stages(self) -> None:
        """单关模式：director 只跑 start_stage 指定的一关，不再自动接续。"""
        self.director.start()
        self.pump(30)

        self.assertEqual(self.director.state, DONE)
        self.assertTrue(self.director.completed)
        self.assertEqual(self.director.cleared_stage, 1)

    def test_reset_returns_to_the_first_stage(self) -> None:
        self.director.start()
        self.pump(12)
        self.director.reset()

        self.assertEqual(self.director.state, DONE)
        self.assertFalse(self.director.started)
        self.assertEqual(self.director.cleared_stage, 0)

        self.director.start()
        self.assertEqual(self.director.stage_number, 1)
        self.assertEqual(self.director.state, BANNER)


if __name__ == "__main__":
    unittest.main()
