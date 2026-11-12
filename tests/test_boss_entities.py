import unittest

from src import config
from src.entities import Boss, PlayerShot


class BossEntityTests(unittest.TestCase):
    def test_boss_bounces_at_horizontal_bounds(self) -> None:
        boss = Boss(config.BOSS_RIGHT_BOUND - 1, config.BOSS_START_Y)
        boss.direction = 1

        boss.update(0.1)

        self.assertEqual(boss.pos.x, config.BOSS_RIGHT_BOUND)
        self.assertEqual(boss.direction, -1)

    def test_boss_changes_phase_at_half_health_and_health_is_clamped(self) -> None:
        boss = Boss(config.SCREEN_W / 2, config.BOSS_START_Y)

        boss.take_damage(boss.max_hp / 2)
        self.assertEqual(boss.phase, 2)

        boss.take_damage(boss.max_hp)
        self.assertEqual(boss.hp, 0)
        self.assertFalse(boss.alive)

    def test_player_shot_moves_up_and_records_previous_position(self) -> None:
        shot = PlayerShot(100, 100)

        shot.update(0.1)

        self.assertEqual(shot.prev_pos.y, 100)
        self.assertLess(shot.pos.y, 100)

    def test_player_shot_is_removed_above_screen(self) -> None:
        shot = PlayerShot(100, 0)

        shot.update(0.1)

        self.assertFalse(shot.alive)


if __name__ == "__main__":
    unittest.main()
