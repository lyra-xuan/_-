"""碰撞调试层的行为测试：开关、当帧统计与绘制副作用。"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pygame

from src import collision, config
from src.entities import Boss, Bullet, Player, PlayerShot
from src.game import Game


class CollisionDebugTests(unittest.TestCase):
    def make_game(self) -> Game:
        game = Game.__new__(Game)
        game.player = Player(config.PLAYER_START_X, config.PLAYER_START_Y)
        game.boss = Boss(config.BOSS_START_X, config.BOSS_START_Y)
        game.bullets = []
        game.player_shots = []
        game.shooting = False
        game.shoot_requested = False
        game.fire_timer = 0.0
        game.boss_attack_timer = config.BOSS_PHASE1_INTERVAL
        game.boss_attack_phase = game.boss.phase
        game.grid = collision.SpatialGrid(
            config.SCREEN_W, config.SCREEN_H, config.GRID_CELL_SIZE
        )
        game.paused = False
        game.scene = Game.SCENE_PLAYING
        game.menu_selection = 0
        game.graze_total = 0
        game.hit_total = 0
        game.hit_flash = 0.0
        game.animation_timer = 0.0
        game.debug_overlay = False
        game.debug_stats = Game._empty_debug_stats()
        game.lives = config.PLAYER_LIVES
        game.invulnerable_timer = 0.0
        game.victory = False
        game.game_over = False
        game.running = True
        stub = pygame.Surface((8, 8), pygame.SRCALPHA)
        game.art = SimpleNamespace(  # type: ignore[assignment]
            hit_spark=stub, graze_ring=stub, boss_burst=stub
        )
        game.effects = []
        game.score = 0
        game.hiscore = 10 ** 9
        game.phase_timer = config.BOSS_PHASE_TIME_LIMIT
        game.boss_flash = 0.0
        game.graze_fx_cooldown = 0.0
        return game

    def dispatch_keys(self, game: Game, *keys: int) -> None:
        events = [
            pygame.event.Event(pygame.KEYDOWN, key=key)
            for key in keys
        ]
        with patch.object(pygame.event, "get", return_value=events):
            game._handle_events()

    def test_default_debug_overlay_is_off(self) -> None:
        self.assertFalse(config.DEBUG_OVERLAY_DEFAULT)

    def test_f2_toggles_debug_overlay_without_touching_pause(self) -> None:
        game = self.make_game()

        self.dispatch_keys(game, pygame.K_F2)
        self.assertTrue(game.debug_overlay)
        self.assertFalse(game.paused)

        self.dispatch_keys(game, pygame.K_F1)
        self.assertTrue(game.debug_overlay)
        self.assertTrue(game.paused)

        self.dispatch_keys(game, pygame.K_F2)
        self.assertFalse(game.debug_overlay)
        self.assertTrue(game.paused)

    def test_debug_stats_count_graze_and_broad_phase_candidates(self) -> None:
        game = self.make_game()
        # 20 像素：在擦弹区（27 + 7.5）内，但在命中区（4.5 + 7.5）外
        bullet = Bullet(
            game.player.pos.x + 20.0, game.player.pos.y, 0.0, 0.0
        )
        bullet.prev_pos.update(bullet.pos)
        game.bullets = [bullet]

        with patch.object(game, "_read_player_input", return_value=(False, False)):
            game.update(0.0)

        self.assertEqual(game.debug_stats["candidates"], 1)
        self.assertEqual(game.debug_stats["grazes"], 1)
        self.assertEqual(game.debug_stats["hits"], 0)
        self.assertTrue(bullet.grazed)
        self.assertEqual(game.graze_total, 1)

    def test_debug_stats_reset_each_frame(self) -> None:
        game = self.make_game()
        bullet = Bullet(
            game.player.pos.x + 20.0, game.player.pos.y, 0.0, 0.0
        )
        bullet.prev_pos.update(bullet.pos)
        game.bullets = [bullet]

        with patch.object(game, "_read_player_input", return_value=(False, False)):
            game.update(0.0)
            self.assertEqual(game.debug_stats["sweeps"], 1)
            # 第二帧：同一颗子弹已擦弹计数过，且已标记 grazed，不再重复计入
            game.update(0.0)

        self.assertEqual(game.debug_stats["grazes"], 0)
        self.assertEqual(game.graze_total, 1)

    def test_debug_stats_count_boss_sweeps_and_hits(self) -> None:
        game = self.make_game()
        shot = PlayerShot(game.boss.pos.x, game.boss.pos.y + 80.0)
        # 构造一帧内跨越 Boss 判定圆的相对运动线段
        shot.prev_pos.update(game.boss.pos.x, game.boss.pos.y + 20.0)
        game.player_shots = [shot]

        game._check_boss_collisions()

        self.assertEqual(game.debug_stats["boss_sweeps"], 1)
        self.assertEqual(game.debug_stats["boss_hits"], 1)
        self.assertLess(game.boss.hp, game.boss.max_hp)

    def test_debug_overlay_drawing_does_not_change_geometry(self) -> None:
        game = self.make_game()
        game.screen = pygame.Surface((config.SCREEN_W, config.SCREEN_H))
        bullet = Bullet(
            game.player.pos.x + 20.0, game.player.pos.y, 0.0, 0.0
        )
        bullet.prev_pos.update(bullet.pos)
        bullet.grazed = True
        game.bullets = [bullet]
        player_pos = game.player.pos.copy()
        player_radii = (game.player.radius, game.player.graze_radius)
        bullet_pos = bullet.pos.copy()
        boss_pos = game.boss.pos.copy()

        game.debug_overlay = True
        game._draw_debug_overlay()

        self.assertEqual(game.player.pos, player_pos)
        self.assertEqual(
            (game.player.radius, game.player.graze_radius), player_radii
        )
        self.assertEqual(bullet.pos, bullet_pos)
        self.assertEqual(bullet.radius, config.BULLET_RADIUS)
        self.assertEqual(game.boss.pos, boss_pos)


if __name__ == "__main__":
    unittest.main()
