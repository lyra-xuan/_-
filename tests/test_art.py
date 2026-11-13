import unittest

import pygame

from src import config
from src.art import GameArt
from src.entities import Player


class GameArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.art = GameArt()

    def test_battle_backgrounds_match_their_layout_regions(self) -> None:
        self.assertEqual(
            self.art.scene_background.get_size(),
            (config.SCREEN_W, config.SCREEN_H),
        )
        self.assertEqual(
            self.art.playfield_background.get_size(),
            (config.PLAYFIELD_WIDTH, config.PLAYFIELD_HEIGHT),
        )
        self.assertEqual(
            self.art.ending_victory.get_size(),
            (config.SCREEN_W, config.SCREEN_H),
        )

    def test_character_and_bullet_sprites_have_transparent_edges(self) -> None:
        self.assertEqual(len(self.art.player_frames), 4)
        self.assertEqual(
            self.art.player_frames[0].get_size(),
            (config.PLAYER_SPRITE_WIDTH, config.PLAYER_SPRITE_HEIGHT),
        )
        self.assertEqual(self.art.player_frames[0].get_at((0, 0)).a, 0)
        self.assertEqual(self.art.boss_portrait.get_at((0, 0)).a, 0)
        self.assertEqual(
            self.art.bullet_small["red"].get_size(), (18, 18)
        )
        self.assertEqual(self.art.player_shot.get_size(), (14, 30))

    def test_red_and_blue_enemy_bullets_use_different_art(self) -> None:
        red = self.art.bullet_small["red"]
        blue = self.art.bullet_small["blue"]

        self.assertNotEqual(red.get_at((9, 9))[:3], blue.get_at((9, 9))[:3])

    def test_sprite_collections_are_complete(self) -> None:
        self.assertEqual(len(self.art.bullet_large), 8)
        self.assertEqual(len(self.art.bullet_small), 4)
        self.assertEqual(len(self.art.bullet_mid), 3)
        self.assertEqual(self.art.hit_spark.get_size(), (44, 44))
        self.assertEqual(self.art.graze_ring.get_size(), (34, 32))
        self.assertEqual(self.art.boss_burst.get_size(), (168, 174))
        self.assertEqual(len(self.art.fairy_frames), 4)
        self.assertEqual(len(self.art.boss_faces), 3)
        self.assertEqual(self.art.boss_faces[0].get_size(), (176, 178))

    def test_player_sprite_drawing_preserves_collision_geometry(self) -> None:
        player = Player(400, 700)
        position = player.pos.copy()
        radius = player.radius
        surface = pygame.Surface((config.SCREEN_W, config.SCREEN_H))

        player.draw(surface, sprite=self.art.player_frames[0])

        self.assertEqual(player.pos, position)
        self.assertEqual(player.radius, radius)


if __name__ == "__main__":
    unittest.main()
