import unittest
from unittest.mock import patch

import pygame
from pygame.math import Vector2

from src import collision, config
from src.entities import Boss, Bullet, Player, PlayerShot
from src.game import Game


class BossCombatTests(unittest.TestCase):
    def make_game(self) -> Game:
        game = Game.__new__(Game)
        game.player = Player(config.SCREEN_W / 2, config.SCREEN_H - 80)
        game.boss = Boss(config.SCREEN_W / 2, config.BOSS_START_Y)
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
        game.graze_total = 0
        game.hit_total = 0
        game.hit_flash = 0.0
        game.victory = False
        game.running = True
        return game

    def test_held_shooting_fires_at_configured_interval(self) -> None:
        game = self.make_game()
        game.shooting = True

        game._spawn_player_shots(0.0)
        game._spawn_player_shots(0.1)
        self.assertEqual(len(game.player_shots), 1)

        game._spawn_player_shots(0.1)
        self.assertEqual(len(game.player_shots), 2)

    def test_quick_z_tap_fires_even_if_key_is_released_before_poll(self) -> None:
        game = self.make_game()
        events = [
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_z),
            pygame.event.Event(pygame.KEYUP, key=pygame.K_z),
        ]

        with patch.object(pygame.event, "get", return_value=events):
            game._handle_events()

        class NoKeys:
            def __getitem__(self, key):
                return False

        with patch.object(pygame.key, "get_pressed", return_value=NoKeys()):
            game.focus, game.shooting = game._read_player_input()
        game._spawn_player_shots(0.0)

        self.assertEqual(len(game.player_shots), 1)

    def test_direction_and_z_input_can_be_active_together(self) -> None:
        game = self.make_game()

        class RightAndZ:
            def __getitem__(self, key):
                return key in (pygame.K_RIGHT, pygame.K_z)

        with patch.object(pygame.key, "get_pressed", return_value=RightAndZ()):
            game.focus, game.shooting = game._read_player_input()

        self.assertEqual(game.player.vel.x, config.PLAYER_SPEED)
        self.assertTrue(game.shooting)

    def test_player_shot_hits_moving_boss_using_relative_sweep(self) -> None:
        game = self.make_game()
        game.boss.prev_pos = Vector2(240, 120)
        game.boss.pos = Vector2(250, 120)
        shot = PlayerShot(245, 120)
        shot.prev_pos = Vector2(245, 155)
        shot.pos = Vector2(245, 85)
        game.player_shots = [shot]

        game._check_boss_collisions()

        self.assertEqual(game.boss.hp, config.BOSS_MAX_HP - shot.damage)
        self.assertFalse(shot.alive)
        self.assertEqual(game.player_shots, [])

    def test_phase_one_fan_and_phase_two_ring_have_expected_counts(self) -> None:
        game = self.make_game()

        game._spawn_boss_attack()
        self.assertEqual(len(game.bullets), config.BOSS_FAN_COUNT)

        game.bullets.clear()
        game.boss.take_damage(game.boss.max_hp / 2)
        game._spawn_boss_attack()
        self.assertEqual(len(game.bullets), config.BOSS_RING_COUNT)

    def test_phase_one_fan_is_aimed_at_player(self) -> None:
        game = self.make_game()
        game._spawn_boss_attack()

        aimed = min(game.bullets, key=lambda bullet: abs(bullet.vel.x))
        self.assertGreater(aimed.vel.y, 0)

    def test_phase_change_uses_phase_two_attack_interval(self) -> None:
        game = self.make_game()
        game.boss.take_damage(game.boss.max_hp / 2)

        game._update_boss_attacks(config.BOSS_PHASE2_INTERVAL - 0.01)
        self.assertEqual(game.bullets, [])

        game._update_boss_attacks(0.02)
        self.assertEqual(len(game.bullets), config.BOSS_RING_COUNT)

    def test_dead_player_shots_are_removed_after_boss_is_defeated(self) -> None:
        game = self.make_game()
        game.boss.alive = False
        shot = PlayerShot(100, 0)
        shot.alive = False
        game.player_shots = [shot]

        game._check_boss_collisions()

        self.assertEqual(game.player_shots, [])

    def test_final_hit_enters_victory_and_clears_projectiles(self) -> None:
        game = self.make_game()
        game.boss.hp = config.PLAYER_SHOT_DAMAGE
        game.bullets = [Bullet(100, 100, 0, 100)]
        shot = PlayerShot(240, 120)
        shot.prev_pos = Vector2(240, 155)
        shot.pos = Vector2(240, 85)
        game.player_shots = [shot]

        game._check_boss_collisions()

        self.assertTrue(game.victory)
        self.assertFalse(game.boss.alive)
        self.assertEqual(game.bullets, [])
        self.assertEqual(game.player_shots, [])

    def test_reset_run_restores_clean_boss_encounter(self) -> None:
        game = self.make_game()
        game.boss.take_damage(game.boss.max_hp)
        game.bullets.append(Bullet(100, 100, 0, 100))
        game.player_shots.append(PlayerShot(100, 100))
        game.paused = True
        game.victory = True
        game.graze_total = 4
        game.hit_total = 2
        game.hit_flash = 0.2
        game.fire_timer = 0.1
        game.boss_attack_timer = 0.1

        game._reset_run()

        self.assertEqual(game.boss.hp, game.boss.max_hp)
        self.assertEqual(game.player.pos.x, config.SCREEN_W / 2)
        self.assertEqual(game.player.pos.y, config.SCREEN_H - 80)
        self.assertEqual(game.bullets, [])
        self.assertEqual(game.player_shots, [])
        self.assertFalse(game.paused)
        self.assertFalse(game.victory)
        self.assertEqual(game.graze_total, 0)
        self.assertEqual(game.hit_total, 0)
        self.assertEqual(game.hit_flash, 0.0)
        self.assertEqual(game.fire_timer, 0.0)
        self.assertEqual(game.boss_attack_timer, config.BOSS_PHASE1_INTERVAL)


if __name__ == "__main__":
    unittest.main()
