"""杂兵妖精推进与音效降级的行为测试。

妖精的出场由关卡波次编排（``StageDirector``）决定，``Game._update_fairies``
只负责推进、按冷却开火与出屏回收，因此这里直接注入妖精再验证行为。
"""
import unittest
from types import SimpleNamespace

import pygame

from src import config
from src.audio import _BGM_ROOT, _MUSIC_FILES, Audio
from src.entities import Fairy, Player
from src.game import Game
from src.spells import Emitter


class FairyTests(unittest.TestCase):
    def test_fairy_drifts_down_and_sways(self) -> None:
        fairy = Fairy(400.0, 100.0, speed=60.0, sway=30.0)

        fairy.update(0.5)

        self.assertAlmostEqual(fairy.pos.y, 130.0)
        self.assertNotAlmostEqual(fairy.pos.x, 400.0)
        self.assertTrue(fairy.alive)

    def test_fairy_is_recycled_after_leaving_the_playfield(self) -> None:
        fairy = Fairy(400.0, config.PLAYFIELD_BOTTOM + 61.0, speed=50.0, sway=0.0)

        fairy.update(0.016)

        self.assertFalse(fairy.alive)

    def test_fairy_draw_without_frames_is_a_no_op(self) -> None:
        surface = pygame.Surface((config.PLAYFIELD_WIDTH, config.PLAYFIELD_HEIGHT))
        before = surface.get_at((400, 100))
        fairy = Fairy(400.0, 100.0, speed=50.0, sway=0.0)

        fairy.draw(surface, None)

        self.assertEqual(surface.get_at((400, 100)), before)

    def make_game(self) -> Game:
        """只搭出 ``_update_fairies`` 需要的几个字段。"""
        game = Game.__new__(Game)
        game.fairies = []
        game.bullets = []
        game.player = Player(config.PLAYER_START_X, config.PLAYER_START_Y)
        stub = pygame.Surface((8, 8), pygame.SRCALPHA)
        game.art = SimpleNamespace(  # type: ignore[assignment]
            bullet_small={"red": stub, "white": stub, "blue": stub},
            bullet_mid={"red": stub, "white": stub},
            bullet_large={"cyan": stub, "magenta": stub},
        )
        return game

    def test_update_fairies_advances_and_reaps_offscreen(self) -> None:
        game = self.make_game()
        fairy = Fairy(400.0, 100.0, speed=60.0, sway=0.0)
        game.fairies = [fairy]

        game._update_fairies(0.5)
        self.assertAlmostEqual(fairy.pos.y, 130.0)
        self.assertEqual(game.fairies, [fairy])

        fairy.pos.y = config.PLAYFIELD_BOTTOM + 61.0
        game._update_fairies(0.016)
        self.assertEqual(game.fairies, [])

    def test_fairy_inside_the_field_fires_into_the_bullet_pool(self) -> None:
        game = self.make_game()
        attack = Emitter(kind="fan", interval=1.5, count=2, step=12.0,
                         speed=200.0, bullet="small_red", aim=True)
        fairy = Fairy(400.0, 200.0, speed=0.0, sway=0.0, attack=attack)
        game.fairies = [fairy]

        game._update_fairies(0.016)

        self.assertEqual(len(game.bullets), attack.count)
        self.assertAlmostEqual(fairy.fire_timer, attack.interval)

    def test_fairy_stays_silent_before_entering_the_playfield(self) -> None:
        game = self.make_game()
        attack = Emitter(kind="fan", interval=1.5, count=2, step=12.0,
                         speed=200.0, bullet="small_red")
        fairy = Fairy(400.0, config.PLAYFIELD_TOP - 40.0, speed=0.0, sway=0.0,
                      attack=attack)
        game.fairies = [fairy]

        game._update_fairies(0.016)

        self.assertEqual(game.bullets, [])


class AudioTests(unittest.TestCase):
    def test_audio_loads_without_raising_when_device_is_missing(self) -> None:
        audio = Audio()

        self.assertIsInstance(audio.sounds, dict)

    def test_playing_an_unknown_sound_is_silent(self) -> None:
        audio = Audio()

        audio.play("does-not-exist")   # 不应抛异常

    def test_bundled_background_music_files_are_present(self) -> None:
        for name in ("title", "stage_select", "stage1", "stage2", "stage3",
                     "boss_rumia", "boss_cirno", "boss_remilia", "boss_sakuya",
                     "ceremony", "ending", "credits"):
            candidates = _MUSIC_FILES[name]
            self.assertTrue(
                any((_BGM_ROOT / c).is_file() for c in candidates),
                f"no file found for {name}",
            )

    def test_missing_music_degrades_silently(self) -> None:
        audio = Audio()
        audio.music_ready = True

        audio.play_music("does-not-exist")

        self.assertIsNone(audio.current_music)

    def test_playing_the_same_track_twice_does_not_restart_it(self) -> None:
        audio = Audio()
        audio.music_ready = True
        audio.current_music = "stage1"

        audio.play_music("stage1")

        self.assertEqual(audio.current_music, "stage1")

    def test_stop_music_is_safe_without_a_device(self) -> None:
        audio = Audio()
        audio.stop_music()

        self.assertIsNone(audio.current_music)


if __name__ == "__main__":
    unittest.main()
