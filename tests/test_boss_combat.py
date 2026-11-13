import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pygame
from pygame.math import Vector2

from src import collision, config
from src.entities import Boss, Bullet, Player, PlayerShot
from src.game import Game


class BossCombatTests(unittest.TestCase):
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
        game.god_mode = False
        game.victory = False
        game.ending_page = 0
        game.game_over = False
        game.running = True
        # 计分与特效：贴图用占位小方块，避免测试里加载整套素材
        stub = pygame.Surface((8, 8), pygame.SRCALPHA)
        game.art = SimpleNamespace(  # type: ignore[assignment]
            hit_spark=stub, graze_ring=stub, boss_burst=stub,
            bullet_small={name: stub for name in ("red", "blue", "white")},
            bullet_large={"magenta": stub},
            item_sprites={kind: stub for kind in config.ITEM_KINDS},
            item_halo=stub,
        )
        game.audio = SimpleNamespace(  # type: ignore[assignment]
            play=lambda name: None,
            play_music=lambda name, fade_ms=600: None,
            stop_music=lambda fade_ms=400: None,
        )
        game.fairies = []
        game.items = []
        game.fairy_timer = config.FAIRY_SPAWN_MIN
        game.effects = []
        game.score = 0
        game.hiscore = 10 ** 9        # 抬高上限，避免测试写盘
        game.power = config.PLAYER_POWER_START
        game.item_total = 0
        game.spiral_angle = 0.0
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

    def test_game_disables_text_input_for_keyboard_controls(self) -> None:
        with (
            patch("pygame.init") as init,
            patch(
                "pygame.display.set_mode",
                return_value=pygame.Surface((config.SCREEN_W, config.SCREEN_H)),
            ) as set_mode,
            patch("pygame.key.stop_text_input") as stop_text_input,
            patch("pygame.display.set_caption"),
            patch("pygame.time.Clock"),
            patch(
                "pygame.image.load",
                side_effect=lambda _: pygame.Surface((640, 480), pygame.SRCALPHA),
            ),
            patch("src.game._load_font"),
        ):
            game = Game()

        init.assert_called_once_with()
        stop_text_input.assert_called_once_with()
        set_mode.assert_called_once_with((1280, 960))
        self.assertEqual(
            game.screen.get_size(), (config.SCREEN_W, config.SCREEN_H)
        )
        self.assertEqual(game.scene, Game.SCENE_TITLE)

    def test_f3_toggles_god_mode(self) -> None:
        game = self.make_game()

        self.dispatch_keys(game, pygame.K_F3)
        self.assertTrue(game.god_mode)

        self.dispatch_keys(game, pygame.K_F3)
        self.assertFalse(game.god_mode)

    def test_title_selection_opens_controls_and_returns(self) -> None:
        game = self.make_game()
        game.scene = Game.SCENE_TITLE

        self.dispatch_keys(game, pygame.K_DOWN, pygame.K_RETURN)
        self.assertEqual(game.scene, Game.SCENE_CONTROLS)

        self.dispatch_keys(game, pygame.K_ESCAPE)
        self.assertEqual(game.scene, Game.SCENE_TITLE)

    def test_manual_pages_can_be_flipped_and_reset_on_open(self) -> None:
        game = self.make_game()
        game.scene = Game.SCENE_TITLE
        game.manual_page = 1

        self.dispatch_keys(game, pygame.K_DOWN, pygame.K_RETURN)
        self.assertEqual(game.scene, Game.SCENE_CONTROLS)
        self.assertEqual(game.manual_page, 0)   # 打开时回到背景说明页

        self.dispatch_keys(game, pygame.K_RIGHT)
        self.assertEqual(game.manual_page, 1)   # 用语解说

        self.dispatch_keys(game, pygame.K_RIGHT)
        self.assertEqual(game.manual_page, 2)   # 操作指南

        self.dispatch_keys(game, pygame.K_RIGHT)
        self.assertEqual(game.manual_page, 2)   # 末页不再翻动

        self.dispatch_keys(game, pygame.K_LEFT, pygame.K_LEFT)
        self.assertEqual(game.manual_page, 0)

    def test_manual_pages_cover_story_terms_and_controls(self) -> None:
        self.assertEqual(Game.MANUAL_PAGES, ("背景说明", "用语解说", "操作指南"))

        terms = {term for term, _ in Game.MANUAL_TERMS}
        for expected in ("幻想乡", "符卡 · Spell Card", "红符 / 红魔法 / 神枪",
                         "擦弹 · Graze", "红玉 · POWER", "青玉 · POINT",
                         "绿玉 · LIFE"):
            self.assertIn(expected, terms)
        for _, meaning in Game.MANUAL_TERMS:
            self.assertTrue(meaning)
        self.assertTrue(Game.MANUAL_STORY)
        self.assertTrue(Game.MANUAL_KEYS)

    def test_victory_afterword_and_credits_include_story_and_thanks(self) -> None:
        self.assertTrue(any("紅霧" in line for line in Game.VICTORY_AFTERWORD))
        self.assertTrue(any("蕾米莉亞" in line for line in Game.VICTORY_AFTERWORD))
        credits = " ".join(
            f"{label} {value}" for label, value in Game.VICTORY_CREDITS
        )
        self.assertIn("Peaceful Romancer", credits)
        self.assertIn("TH06", credits)
        self.assertIn("lyra", credits)
        self.assertNotIn("用户提供", credits)
        self.assertIn("ありがとう", " ".join(Game.VICTORY_THANKS))

    def test_title_info_panel_is_compact_in_the_upper_left(self) -> None:
        left, top, width, height = Game.TITLE_INFO_PANEL_RECT

        self.assertLess(left, config.SCREEN_W / 4)
        self.assertLess(top, config.SCREEN_H / 4)
        self.assertLess(width, 600)
        self.assertLess(top + height, config.SCREEN_H)

    def test_music_switches_from_title_to_stage_and_then_to_boss(self) -> None:
        game = self.make_game()
        played: list[str] = []
        game.audio = SimpleNamespace(  # type: ignore[assignment]
            play=lambda name: None,
            play_music=played.append,
            stop_music=lambda fade_ms=400: None,
        )

        game.scene = Game.SCENE_TITLE
        game._update_music()
        game.scene = Game.SCENE_PLAYING
        game._update_music()
        game.boss.hp = game.boss.max_hp / 4.0     # 进入第三段符卡
        game._update_music()
        game.victory = True
        game._update_music()

        self.assertEqual(played, ["title", "stage", "boss", "ending"])

    def test_title_enter_starts_the_boss_fight(self) -> None:
        game = self.make_game()
        game.scene = Game.SCENE_TITLE

        self.dispatch_keys(game, pygame.K_RETURN)

        self.assertEqual(game.scene, Game.SCENE_PLAYING)
        self.assertEqual(game.entry_card_timer, Game.ENTRY_CARD_DURATION)

    def test_entry_card_holds_combat_until_it_fades(self) -> None:
        game = self.make_game()
        game.entry_card_timer = Game.ENTRY_CARD_DURATION
        boss_position = game.boss.pos.copy()
        player_position = game.player.pos.copy()
        attack_timer = game.boss_attack_timer

        game.update(0.5)

        self.assertAlmostEqual(
            game.entry_card_timer, Game.ENTRY_CARD_DURATION - 0.5
        )
        self.assertEqual(game.boss.pos, boss_position)
        self.assertEqual(game.player.pos, player_position)
        self.assertEqual(game.boss_attack_timer, attack_timer)

    def test_title_exit_item_and_escape_close_the_game(self) -> None:
        game = self.make_game()
        game.scene = Game.SCENE_TITLE
        self.dispatch_keys(game, pygame.K_UP, pygame.K_RETURN)
        self.assertFalse(game.running)

        game = self.make_game()
        game.scene = Game.SCENE_TITLE
        self.dispatch_keys(game, pygame.K_ESCAPE)
        self.assertFalse(game.running)

    def test_gameplay_does_not_advance_while_on_title(self) -> None:
        game = self.make_game()
        game.scene = Game.SCENE_TITLE
        boss_position = game.boss.pos.copy()
        attack_timer = game.boss_attack_timer

        game.update(1.0)

        self.assertEqual(game.boss.pos, boss_position)
        self.assertEqual(game.boss_attack_timer, attack_timer)
        self.assertEqual(game.bullets, [])

    def test_player_is_clamped_to_the_bullet_playfield(self) -> None:
        game = self.make_game()
        game.player.pos.update(
            config.PLAYFIELD_LEFT - 20, config.PLAYFIELD_BOTTOM + 20
        )

        with patch.object(game, "_read_player_input", return_value=(False, False)):
            game.update(0.0)

        self.assertEqual(
            game.player.pos.x, config.PLAYFIELD_LEFT + game.player.radius
        )
        self.assertEqual(
            game.player.pos.y, config.PLAYFIELD_BOTTOM - game.player.radius
        )


    def test_f1_toggles_pause_and_space_does_not(self) -> None:
        game = self.make_game()

        with patch.object(
            pygame.event,
            "get",
            return_value=[pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)],
        ):
            game._handle_events()
        self.assertFalse(game.paused)

        with patch.object(
            pygame.event,
            "get",
            return_value=[pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1)],
        ):
            game._handle_events()
        self.assertTrue(game.paused)

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
        # 阶段 2 是双层环：外圈大玉 + 两倍数量的内圈小玉
        self.assertEqual(len(game.bullets), config.BOSS_RING_COUNT * 3)

    def test_phase_two_rings_spawn_from_the_boss_body_anchor(self) -> None:
        game = self.make_game()
        game.boss.take_damage(game.boss.max_hp / 2)
        origin = game._boss_attack_origin()

        game._spawn_boss_attack()

        self.assertEqual(len(game.bullets), config.BOSS_RING_COUNT * 3)
        self.assertTrue(all(bullet.pos == origin for bullet in game.bullets))
        self.assertEqual(
            origin.y,
            game.boss.pos.y + config.BOSS_ATTACK_ORIGIN_OFFSET[1],
        )

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
        self.assertEqual(len(game.bullets), config.BOSS_RING_COUNT * 3)

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
        boss_x = config.BOSS_START_X
        shot = PlayerShot(boss_x, config.BOSS_START_Y)
        shot.prev_pos = Vector2(boss_x, config.BOSS_START_Y + 35)
        shot.pos = Vector2(boss_x, config.BOSS_START_Y - 35)
        game.player_shots = [shot]

        game._check_boss_collisions()

        self.assertTrue(game.victory)
        self.assertEqual(game.ending_page, 0)
        self.assertFalse(game.boss.alive)
        self.assertEqual(game.bullets, [])
        self.assertEqual(game.player_shots, [])

    def test_player_hit_consumes_life_clears_bullets_and_respawns(self) -> None:
        game = self.make_game()
        bullet = Bullet(100, 100, 0, 100)
        game.bullets = [bullet]
        game.player.graze_count = 3
        hit_position = Vector2(400, 500)
        game.player.pos = hit_position
        game.player.prev_pos = Vector2(hit_position)

        game._on_player_hit(bullet)

        self.assertEqual(game.lives, config.PLAYER_LIVES - 1)
        self.assertEqual(game.invulnerable_timer, config.PLAYER_INVULNERABLE_TIME)
        self.assertEqual(game.bullets, [])
        self.assertEqual(
            game.player.pos,
            Vector2(config.PLAYER_START_X, config.PLAYER_START_Y),
        )
        self.assertEqual(game.player.prev_pos, game.player.pos)
        self.assertEqual(game.player.graze_count, 0)
        self.assertEqual(game.hit_total, 1)
        self.assertFalse(game.game_over)

    def test_invulnerability_prevents_another_hit(self) -> None:
        game = self.make_game()
        game.invulnerable_timer = config.PLAYER_INVULNERABLE_TIME / 2
        bullet = Bullet(game.player.pos.x, game.player.pos.y, 0, 0)
        game.bullets = [bullet]

        game._check_collisions()

        self.assertEqual(game.lives, config.PLAYER_LIVES)
        self.assertEqual(game.hit_total, 0)
        self.assertTrue(bullet.alive)

    def test_god_mode_prevents_bullet_hits_without_spending_lives(self) -> None:
        game = self.make_game()
        game.god_mode = True
        bullet = Bullet(game.player.pos.x, game.player.pos.y, 0, 0)
        game.bullets = [bullet]

        game._check_collisions()

        self.assertEqual(game.lives, config.PLAYER_LIVES)
        self.assertEqual(game.hit_total, 0)
        self.assertTrue(bullet.alive)
        self.assertFalse(game.game_over)

    def test_invulnerability_timer_counts_down_during_play(self) -> None:
        game = self.make_game()
        game.invulnerable_timer = config.PLAYER_INVULNERABLE_TIME

        with patch.object(game, "_read_player_input", return_value=(False, False)):
            game.update(0.5)

        self.assertAlmostEqual(
            game.invulnerable_timer,
            config.PLAYER_INVULNERABLE_TIME - 0.5,
        )

    def test_last_life_enters_game_over_and_clears_combat(self) -> None:
        game = self.make_game()
        game.lives = 1
        game.bullets = [Bullet(100, 100, 0, 100)]
        game.player_shots = [PlayerShot(100, 100)]
        bullet = Bullet(200, 200, 0, 100)

        game._on_player_hit(bullet)

        self.assertEqual(game.lives, 0)
        self.assertTrue(game.game_over)
        self.assertEqual(game.bullets, [])
        self.assertEqual(game.player_shots, [])
        self.assertFalse(game.shooting)
        self.assertEqual(game.invulnerable_timer, 0.0)

    def test_game_over_freezes_boss_and_attack_timer(self) -> None:
        game = self.make_game()
        game.game_over = True
        boss_position = game.boss.pos.copy()
        attack_timer = game.boss_attack_timer

        game.update(1.0)

        self.assertEqual(game.boss.pos, boss_position)
        self.assertEqual(game.boss_attack_timer, attack_timer)
        self.assertEqual(game.bullets, [])

    def test_game_over_r_restarts_a_clean_run(self) -> None:
        game = self.make_game()
        game.game_over = True
        game.lives = 0
        game.invulnerable_timer = 0.5
        game.boss.take_damage(game.boss.max_hp)

        self.dispatch_keys(game, pygame.K_r)

        self.assertFalse(game.game_over)
        self.assertFalse(game.victory)
        self.assertEqual(game.scene, Game.SCENE_PLAYING)
        self.assertEqual(game.lives, config.PLAYER_LIVES)
        self.assertEqual(game.invulnerable_timer, 0.0)
        self.assertEqual(game.boss.hp, config.BOSS_MAX_HP)

    def test_game_over_enter_and_escape_return_to_title(self) -> None:
        for key in (pygame.K_RETURN, pygame.K_ESCAPE):
            with self.subTest(key=key):
                game = self.make_game()
                game.game_over = True

                self.dispatch_keys(game, key)

                self.assertEqual(game.scene, Game.SCENE_TITLE)
                self.assertFalse(game.game_over)
                self.assertTrue(game.running)

    def test_victory_pages_can_be_read_then_closed(self) -> None:
        game = self.make_game()
        game.victory = True

        self.dispatch_keys(game, pygame.K_RETURN)
        self.assertEqual(game.ending_page, 1)
        self.assertEqual(game.scene, Game.SCENE_PLAYING)
        self.dispatch_keys(game, pygame.K_RIGHT)
        self.assertEqual(game.ending_page, 2)
        self.dispatch_keys(game, pygame.K_LEFT)
        self.assertEqual(game.ending_page, 1)
        self.dispatch_keys(game, pygame.K_RETURN)
        self.assertEqual(game.ending_page, 2)

        self.dispatch_keys(game, pygame.K_RETURN)
        self.assertEqual(game.scene, Game.SCENE_TITLE)
        self.assertFalse(game.victory)
        self.assertTrue(game.running)

    def test_victory_escape_returns_to_title_from_any_page(self) -> None:
        game = self.make_game()
        game.victory = True
        game.ending_page = 1

        self.dispatch_keys(game, pygame.K_ESCAPE)

        self.assertEqual(game.scene, Game.SCENE_TITLE)
        self.assertFalse(game.victory)

    def test_reset_run_restores_clean_boss_encounter(self) -> None:
        game = self.make_game()
        game.boss.take_damage(game.boss.max_hp)
        game.bullets.append(Bullet(100, 100, 0, 100))
        game.player_shots.append(PlayerShot(100, 100))
        game.paused = True
        game.victory = True
        game.ending_page = 2
        game.graze_total = 4
        game.hit_total = 2
        game.hit_flash = 0.2
        game.lives = 1
        game.invulnerable_timer = 0.8
        game.game_over = True
        game.fire_timer = 0.1
        game.boss_attack_timer = 0.1

        game._reset_run()

        self.assertEqual(game.boss.hp, game.boss.max_hp)
        self.assertEqual(game.player.pos.x, config.PLAYER_START_X)
        self.assertEqual(game.player.pos.y, config.PLAYER_START_Y)
        self.assertEqual(game.bullets, [])
        self.assertEqual(game.player_shots, [])
        self.assertFalse(game.paused)
        self.assertFalse(game.victory)
        self.assertEqual(game.ending_page, 0)
        self.assertFalse(game.game_over)
        self.assertEqual(game.lives, config.PLAYER_LIVES)
        self.assertEqual(game.invulnerable_timer, 0.0)
        self.assertEqual(game.graze_total, 0)
        self.assertEqual(game.hit_total, 0)
        self.assertEqual(game.hit_flash, 0.0)
        self.assertEqual(game.fire_timer, 0.0)
        self.assertEqual(game.boss_attack_timer, config.BOSS_PHASE1_INTERVAL)
        self.assertEqual(game.entry_card_timer, Game.ENTRY_CARD_DURATION)


if __name__ == "__main__":
    unittest.main()
