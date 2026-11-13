import unittest

from pygame.math import Vector2

from src import collision, config
from src.entities import Bullet, Player
from src.game import Game


class CollisionSweepTests(unittest.TestCase):
    def make_game(self, player: Player, bullets: list[Bullet]) -> Game:
        game = Game.__new__(Game)
        game.player = player
        game.bullets = bullets
        game.grid = collision.SpatialGrid(
            config.SCREEN_W, config.SCREEN_H, config.GRID_CELL_SIZE
        )
        game.graze_total = 0
        game.hit_total = 0
        game.hit_flash = 0.0
        game.lives = config.PLAYER_LIVES
        game.invulnerable_timer = 0.0
        game.game_over = False
        game.debug_stats = Game._empty_debug_stats()
        return game

    def test_swept_graze_crossing_grid_boundary_is_not_filtered(self) -> None:
        player = Player(240.0, 552.0)
        player.prev_pos = Vector2(player.pos)
        bullet = Bullet(240.0, 580.0, 0.0, 150.0)
        bullet.prev_pos = Vector2(240.0, 575.0)
        game = self.make_game(player, [bullet])

        game._check_collisions()

        self.assertTrue(bullet.grazed)
        self.assertEqual(game.graze_total, 1)

    def test_player_motion_is_included_in_hit_sweep(self) -> None:
        player = Player(109.3333333333, 560.0)
        player.prev_pos = Vector2(100.0, 560.0)
        bullet = Bullet(97.1793, 557.488, 0.0, 150.0)
        bullet.prev_pos = Vector2(97.1793, 552.488)
        game = self.make_game(player, [bullet])

        game._check_collisions()

        self.assertEqual(game.hit_total, 1)
        self.assertFalse(bullet.alive)


if __name__ == "__main__":
    unittest.main()
