import unittest

from pygame.math import Vector2

from src import config
from src.entities import Boss, Player, PlayerShot
from src.game import Game


class BossCombatTests(unittest.TestCase):
    def make_game(self) -> Game:
        game = Game.__new__(Game)
        game.player = Player(config.SCREEN_W / 2, config.SCREEN_H - 80)
        game.boss = Boss(config.SCREEN_W / 2, config.BOSS_START_Y)
        game.bullets = []
        game.player_shots = []
        game.shooting = False
        game.fire_timer = 0.0
        game.boss_attack_timer = config.BOSS_PHASE1_INTERVAL
        game.boss_attack_phase = game.boss.phase
        game.victory = False
        return game

    def test_held_shooting_fires_at_configured_interval(self) -> None:
        game = self.make_game()
        game.shooting = True

        game._spawn_player_shots(0.0)
        game._spawn_player_shots(0.1)
        self.assertEqual(len(game.player_shots), 1)

        game._spawn_player_shots(0.1)
        self.assertEqual(len(game.player_shots), 2)

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


if __name__ == "__main__":
    unittest.main()
