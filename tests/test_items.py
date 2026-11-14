"""掉落道具、火力成长、可击破妖精与第三符卡的行为测试。"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pygame
from pygame.math import Vector2

from src import collision, config
from src.director import BANNER, StageDirector
from src.entities import Boss, Fairy, Item, Player, PlayerShot
from src.game import Game


def make_game() -> Game:
    """构造一个脱离素材与真实 __init__ 的最小 Game。"""
    game = Game.__new__(Game)
    game.player = Player(config.PLAYER_START_X, config.PLAYER_START_Y)
    game.boss = Boss(config.BOSS_START_X, config.BOSS_START_Y)
    game.director = StageDirector()
    game.bullets = []
    game.player_shots = []
    game.fairies = []
    game.fairy_kill_count = 0
    game.items = []
    game.effects = []
    game.shooting = False
    game.shoot_requested = False
    game.focus = False
    game.fire_timer = 0.0
    game.boss_attack_phase = 0
    game.spell_timers = []
    game.spell_imperilled = False
    game.spell_timed_out = False
    game.spells_captured = 0
    game.spells_failed = 0
    game.awarded_clear = 0
    game.grid = collision.SpatialGrid(
        config.SCREEN_W, config.SCREEN_H, config.GRID_CELL_SIZE
    )
    game.paused = False
    game.scene = Game.SCENE_PLAYING
    game.graze_total = 0
    game.hit_total = 0
    game.hit_flash = 0.0
    game.animation_timer = 0.0
    game.debug_overlay = False
    game.debug_stats = Game._empty_debug_stats()
    game.lives = config.PLAYER_LIVES
    game.bombs = config.PLAYER_BOMB_START
    game.bomb_timer = 0.0
    game.invulnerable_timer = 0.0
    game.god_mode = False
    game.victory = False
    game.ending_page = 0
    game.game_over = False
    game.running = True
    game.score = 0
    game.hiscore = 10 ** 9
    game.power = config.PLAYER_POWER_START
    game.item_total = 0
    game.phase_timer = config.BOSS_PHASE_TIME_LIMIT
    game.boss_flash = 0.0
    game.graze_fx_cooldown = 0.0

    stub = pygame.Surface((8, 8), pygame.SRCALPHA)
    game.art = SimpleNamespace(  # type: ignore[assignment]
        hit_spark=stub, graze_ring=stub, boss_burst=stub,
        bullet_small={name: stub for name in ("red", "blue", "white")},
        bullet_mid={name: stub for name in ("red", "white")},
        bullet_large={"magenta": stub, "cyan": stub},
        item_sprites={kind: stub for kind in config.ITEM_KINDS},
        item_halo=stub,
    )
    game.audio = SimpleNamespace(  # type: ignore[assignment]
        play=lambda name: None,
        play_music=lambda name, fade_ms=600: None,
        stop_music=lambda fade_ms=400: None,
    )
    return game


class ItemMotionTests(unittest.TestCase):
    def test_item_falls_at_constant_speed_when_far_from_the_player(self) -> None:
        item = Item(400.0, 100.0, "point")

        item.update(0.5)

        self.assertAlmostEqual(item.pos.y, 100.0 + config.ITEM_FALL_SPEED * 0.5)
        self.assertTrue(item.alive)

    def test_item_is_recycled_below_the_playfield(self) -> None:
        item = Item(400.0, config.PLAYFIELD_BOTTOM + 41.0, "point")

        item.update(0.016)

        self.assertFalse(item.alive)

    def test_item_magnetises_toward_a_nearby_player(self) -> None:
        game = make_game()
        game.player.pos = Vector2(400.0, 700.0)
        game.player.prev_pos = Vector2(game.player.pos)
        item = Item(460.0, 700.0, "point")
        game.items = [item]

        game._update_items(0.05)

        self.assertLess(item.pos.x, 460.0)
        self.assertAlmostEqual(item.pos.y, 700.0)
        self.assertTrue(item.alive)

    def test_item_is_collected_once_it_touches_the_player(self) -> None:
        game = make_game()
        game.player.pos = Vector2(400.0, 700.0)
        item = Item(405.0, 700.0, "point")
        game.items = [item]

        game._update_items(0.0)

        self.assertEqual(game.items, [])
        self.assertEqual(game.item_total, 1)
        self.assertEqual(game.score, config.ITEM_POINT_SCORE)


class ItemEffectTests(unittest.TestCase):
    def deep_collect(self, game: Game, kind: str) -> None:
        game._collect_item(Item(100.0, 100.0, kind))

    def test_power_item_raises_power(self) -> None:
        game = make_game()
        game.power = 1.0

        self.deep_collect(game, "power")

        self.assertAlmostEqual(game.power, 1.0 + config.ITEM_POWER_GAIN)
        self.assertEqual(game.item_total, 1)

    def test_power_item_is_capped_at_maximum(self) -> None:
        game = make_game()
        game.power = config.ITEM_POWER_MAX - 0.01

        self.deep_collect(game, "power")

        self.assertEqual(game.power, config.ITEM_POWER_MAX)

    def test_power_item_at_maximum_converts_to_score(self) -> None:
        game = make_game()
        game.power = config.ITEM_POWER_MAX

        self.deep_collect(game, "power")

        self.assertEqual(game.power, config.ITEM_POWER_MAX)
        self.assertEqual(game.score, config.ITEM_POWER_FULL_SCORE)

    def test_life_item_restores_a_lost_life_without_exceeding_the_cap(self) -> None:
        game = make_game()
        game.lives = 1

        self.deep_collect(game, "life")
        self.assertEqual(game.lives, 2)

        game.lives = config.PLAYER_LIVES
        self.deep_collect(game, "life")
        self.assertEqual(game.lives, config.PLAYER_LIVES)


class PowerSpreadTests(unittest.TestCase):
    def test_shot_offsets_grow_with_power(self) -> None:
        game = make_game()

        game.power = config.PLAYER_POWER_START
        self.assertEqual(len(game._shot_offsets()), 1)

        game.power = config.PLAYER_POWER_DOUBLE
        self.assertEqual(len(game._shot_offsets()), 2)

        game.power = config.ITEM_POWER_MAX
        self.assertEqual(len(game._shot_offsets()), 4)

    def test_full_power_fires_four_shots_per_volley(self) -> None:
        game = make_game()
        game.power = config.ITEM_POWER_MAX
        game.shooting = True

        game._spawn_player_shots(0.0)

        self.assertEqual(len(game.player_shots), 4)


class FairyCombatTests(unittest.TestCase):
    def test_fairy_is_defeated_and_drops_a_point_item(self) -> None:
        game = make_game()
        fairy = Fairy(400.0, 300.0, speed=0.0, sway=0.0)
        game.fairies = [fairy]
        shot = PlayerShot(400.0, 320.0)
        shot.prev_pos = Vector2(400.0, 340.0)
        shot.pos = Vector2(400.0, 320.0)
        fairy.hp = shot.damage
        game.player_shots = [shot]

        with patch("src.game.random.random", return_value=0.99):
            game._check_fairy_collisions()

        self.assertEqual(game.fairies, [])
        self.assertEqual(game.player_shots, [])
        self.assertEqual(len(game.items), config.FAIRY_POINT_DROPS)
        self.assertEqual(game.items[0].kind, "point")

    def test_fairy_loot_rotates_between_point_and_power(self) -> None:
        game = make_game()
        fairy = Fairy(400.0, 300.0, speed=0.0, sway=0.0)

        with patch("src.game.random.random", return_value=0.99):
            for _ in range(3):
                game._on_fairy_defeated(fairy)

        self.assertEqual(
            [item.kind for item in game.items], ["point", "power", "point"]
        )

    def test_fairy_can_rarely_drop_an_extra_life(self) -> None:
        game = make_game()
        fairy = Fairy(400.0, 300.0, speed=0.0, sway=0.0)

        with patch("src.game.random.random", return_value=0.0):
            game._on_fairy_defeated(fairy)

        self.assertEqual(game.items[0].kind, "life")

    def test_fairy_survives_a_non_lethal_hit(self) -> None:
        game = make_game()
        fairy = Fairy(400.0, 300.0, speed=0.0, sway=0.0)
        fairy.hp = config.FAIRY_HP
        game.fairies = [fairy]
        shot = PlayerShot(400.0, 320.0)
        shot.prev_pos = Vector2(400.0, 340.0)
        shot.pos = Vector2(400.0, 320.0)
        game.player_shots = [shot]

        game._check_fairy_collisions()

        self.assertEqual(len(game.fairies), 1)
        self.assertAlmostEqual(fairy.hp, config.FAIRY_HP - shot.damage)
        self.assertEqual(game.items, [])


class SpellPhaseTests(unittest.TestCase):
    """符卡切换：生命分段、换符卡掉落、超时推进。"""

    def test_boss_health_splits_evenly_across_the_spell_cards(self) -> None:
        boss = Boss(config.BOSS_START_X, config.BOSS_START_Y)
        segment = boss.max_hp / boss.spell_count

        self.assertEqual(boss.phase, 1)
        for expected in range(2, boss.spell_count + 1):
            boss.take_damage(segment)
            self.assertEqual(boss.phase, expected)
            self.assertTrue(boss.alive)
        boss.take_damage(segment)
        self.assertFalse(boss.alive)

    def test_entering_a_new_spell_drops_power_items(self) -> None:
        game = make_game()
        # 第一张符卡「展开」时不结算、不掉落
        game._update_boss_attacks(0.0)
        self.assertEqual(game.items, [])
        self.assertEqual(game.boss_attack_phase, 1)

        # 把生命推到第二张符卡，再次推进即触发换卡
        segment = game.boss.max_hp / game.boss.spell_count
        game.boss.take_damage(segment + 0.5)
        self.assertEqual(game.boss.phase, 2)

        game._update_boss_attacks(0.0)

        self.assertEqual(len(game.items), config.BOSS_PHASE_DROP_POWER)
        self.assertTrue(all(item.kind == "power" for item in game.items))
        self.assertEqual(game.spells_captured, 1)

    def test_entering_the_last_spell_also_drops_a_life_item(self) -> None:
        game = make_game()
        game._update_boss_attacks(0.0)
        segment = game.boss.max_hp / game.boss.spell_count
        game.boss.take_damage(segment * (game.boss.spell_count - 1) + 0.5)
        self.assertEqual(game.boss.phase, game.boss.spell_count)

        game._update_boss_attacks(0.0)

        kinds = {item.kind for item in game.items}
        self.assertIn("life", kinds)

    def test_force_phase_end_walks_to_the_next_card_then_defeats_the_boss(
            self) -> None:
        game = make_game()

        game._force_phase_end()
        self.assertEqual(game.boss.phase, 2)
        self.assertTrue(game.boss.alive)
        self.assertTrue(game.spell_timed_out)

        game._force_phase_end()
        self.assertEqual(game.boss.phase, 3)
        self.assertTrue(game.boss.alive)

        game._force_phase_end()
        self.assertEqual(game.boss.hp, 0.0)
        self.assertFalse(game.boss.alive)


class ResetRunTests(unittest.TestCase):
    def test_reset_run_restores_power_and_clears_items(self) -> None:
        game = make_game()
        game.power = 3.5
        game.item_total = 7
        game.boss.spell_angle = 1.2
        game.items = [Item(100.0, 100.0, "power")]

        game._reset_run()

        self.assertEqual(game.power, config.PLAYER_POWER_START)
        self.assertEqual(game.item_total, 0)
        self.assertEqual(game.items, [])
        self.assertIsNone(game.boss)
        self.assertEqual(game.director.state, BANNER)


if __name__ == "__main__":
    unittest.main()
