"""装饰性小妖精与音效降级的行为测试。"""
import unittest

import pygame

from src import config
from src.audio import _BGM_ROOT, _MUSIC_FILES, Audio
from src.entities import Fairy
from src.game import Game


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

    def test_update_fairies_spawns_on_timer_and_reaps_offscreen(self) -> None:
        game = Game.__new__(Game)
        game.fairies = []
        game.fairy_timer = 0.0

        game._update_fairies(0.0)
        self.assertEqual(len(game.fairies), 1)
        self.assertGreaterEqual(
            game.fairy_timer, config.FAIRY_SPAWN_MIN
        )

        game.fairies[0].pos.y = config.PLAYFIELD_BOTTOM + 61.0
        game._update_fairies(0.016)
        self.assertEqual(game.fairies, [])


class AudioTests(unittest.TestCase):
    def test_audio_loads_without_raising_when_device_is_missing(self) -> None:
        audio = Audio()

        self.assertIsInstance(audio.sounds, dict)

    def test_playing_an_unknown_sound_is_silent(self) -> None:
        audio = Audio()

        audio.play("does-not-exist")   # 不应抛异常

    def test_bundled_background_music_files_are_present(self) -> None:
        for name in ("title", "stage", "boss", "ending"):
            self.assertTrue((_BGM_ROOT / _MUSIC_FILES[name]).is_file(), name)

    def test_missing_music_degrades_silently(self) -> None:
        audio = Audio()
        audio.music_ready = True

        audio.play_music("does-not-exist")

        self.assertIsNone(audio.current_music)

    def test_playing_the_same_track_twice_does_not_restart_it(self) -> None:
        audio = Audio()
        audio.music_ready = True
        audio.current_music = "stage"

        audio.play_music("stage")

        self.assertEqual(audio.current_music, "stage")

    def test_stop_music_is_safe_without_a_device(self) -> None:
        audio = Audio()
        audio.stop_music()

        self.assertIsNone(audio.current_music)


if __name__ == "__main__":
    unittest.main()
