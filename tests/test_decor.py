"""装饰性小妖精与音效降级的行为测试。"""
import unittest

import pygame

from src import config
from src.audio import Audio
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


if __name__ == "__main__":
    unittest.main()
