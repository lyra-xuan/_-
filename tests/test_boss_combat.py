"""Boss 战、符卡结算、灵击与各场景输入的集成测试。

弹幕不再是「阶段 1 / 2 / 3」的硬编码分支，而是 :mod:`src.spells` 里的
``SpellCard`` 数据；关卡推进交给 :class:`~src.director.StageDirector`。这里的
``make_game`` 直接组装一个「已在游戏中」的 ``Game``，绕过窗口与素材加载。
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pygame
from pygame.math import Vector2

from src import collision, config
from src.director import BANNER, DONE, FIGHT, StageDirector
from src.entities import Boss, Bullet, Player, PlayerShot
from src.game import Game


def make_game() -> Game:
    """组装一个处于游戏中的 ``Game``，只补齐被测逻辑需要的字段。"""
    game = Game.__new__(Game)
    game.player = Player(config.PLAYER_START_X, config.PLAYER_START_Y)
    game.boss = Boss(config.BOSS_START_X, config.BOSS_START_Y)
    game.director = StageDirector()
    game.bullets = []
    game.player_shots = []
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
    game.phase_timer = config.BOSS_PHASE_TIME_LIMIT
    game.grid = collision.SpatialGrid(
        config.SCREEN_W, config.SCREEN_H, config.GRID_CELL_SIZE
    )
    game.paused = False
    game.scene = Game.SCENE_PLAYING
    game.menu_selection = 0
    game.manual_page = 0
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
    game.cheat_prompt_active = False
    game.cheat_input = ""
    game.victory = False
    game.ending_page = 0
    game.game_over = False
    game.running = True
    game.unlocked_stage = 1
    game.all_cleared = False
    game.stage_select_index = 0
    game.afterword_only = False
    # 计分与特效：贴图用占位小方块，避免测试里加载整套素材
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
    game.fairies = []
    game.fairy_kill_count = 0
    game.items = []
    game.effects = []
    game.score = 0
    game.hiscore = 10 ** 9        # 抬高上限，避免测试写盘
    game.power = config.PLAYER_POWER_START
    game.item_total = 0
    game.boss_flash = 0.0
    game.graze_fx_cooldown = 0.0
    return game


def dispatch_keys(game: Game, *keys: int) -> None:
    events = [
        pygame.event.Event(pygame.KEYDOWN, key=key)
        for key in keys
    ]
    with patch.object(pygame.event, "get", return_value=events):
        game._handle_events()


class MenuAndStoryTests(unittest.TestCase):
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

    def test_f3_requires_password_to_toggle_god_mode(self) -> None:
        game = make_game()

        # 按 F3 只弹出密码框，不直接解锁
        dispatch_keys(game, pygame.K_F3)
        self.assertFalse(game.god_mode)
        self.assertTrue(game.cheat_prompt_active)

        # 输入正确密码 472977 → 解锁无敌
        dispatch_keys(game, pygame.K_4, pygame.K_7, pygame.K_2,
                      pygame.K_9, pygame.K_7, pygame.K_7)
        self.assertTrue(game.god_mode)
        self.assertFalse(game.cheat_prompt_active)

        # 再次按 F3 并输入密码 → 关闭无敌
        dispatch_keys(game, pygame.K_F3)
        dispatch_keys(game, pygame.K_4, pygame.K_7, pygame.K_2,
                      pygame.K_9, pygame.K_7, pygame.K_7)
        self.assertFalse(game.god_mode)

    def test_wrong_cheat_password_does_not_toggle_god_mode(self) -> None:
        game = make_game()

        dispatch_keys(game, pygame.K_F3)
        dispatch_keys(game, pygame.K_0, pygame.K_0, pygame.K_0,
                      pygame.K_0, pygame.K_0, pygame.K_0)
        self.assertFalse(game.god_mode)
        self.assertFalse(game.cheat_prompt_active)

    def test_title_selection_opens_controls_and_returns(self) -> None:
        game = make_game()
        game.scene = Game.SCENE_TITLE

        dispatch_keys(game, pygame.K_DOWN, pygame.K_DOWN, pygame.K_RETURN)
        self.assertEqual(game.scene, Game.SCENE_CONTROLS)

        dispatch_keys(game, pygame.K_ESCAPE)
        self.assertEqual(game.scene, Game.SCENE_TITLE)

    def test_manual_pages_can_be_flipped_and_reset_on_open(self) -> None:
        game = make_game()
        game.scene = Game.SCENE_TITLE
        game.manual_page = 1

        dispatch_keys(game, pygame.K_DOWN, pygame.K_DOWN, pygame.K_RETURN)
        self.assertEqual(game.scene, Game.SCENE_CONTROLS)
        self.assertEqual(game.manual_page, 0)   # 打开时回到背景说明页

        dispatch_keys(game, pygame.K_RIGHT)
        self.assertEqual(game.manual_page, 1)   # 用语解说

        dispatch_keys(game, pygame.K_RIGHT)
        self.assertEqual(game.manual_page, 2)   # 操作指南

        dispatch_keys(game, pygame.K_RIGHT)
        self.assertEqual(game.manual_page, 2)   # 末页不再翻动

        dispatch_keys(game, pygame.K_LEFT, pygame.K_LEFT)
        self.assertEqual(game.manual_page, 0)

    def test_manual_pages_cover_stage_terms_and_controls(self) -> None:
        self.assertEqual(Game.MANUAL_PAGES, ("背景说明", "用语解说", "操作指南"))

        terms = {term for term, _ in Game.MANUAL_TERMS}
        for expected in ("幻想乡", "符卡 · Spell Card", "中 Boss", "关底 Boss",
                         "擦弹 · Graze", "灵击 · Spell Card", "红玉 · POWER",
                         "青玉 · POINT", "绿玉 · LIFE"):
            self.assertIn(expected, terms)
        for _, meaning in Game.MANUAL_TERMS:
            self.assertTrue(meaning)
        self.assertTrue(Game.MANUAL_STORY)
        self.assertTrue(Game.MANUAL_KEYS)

    def test_victory_afterword_and_credits_include_story_and_thanks(self) -> None:
        all_afterword = [
            line for page in Game.VICTORY_AFTERWORD_PAGES for line in page
        ]
        self.assertTrue(any("紅霧" in line for line in all_afterword))
        self.assertTrue(any("蕾米莉亞" in line for line in all_afterword))
        credits = " ".join(
            f"{label} {value}" for label, value in Game.VICTORY_CREDITS
        )
        self.assertIn("ZUN", credits)
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


class MusicTests(unittest.TestCase):
    def test_music_switches_from_title_to_stage_and_then_to_boss(self) -> None:
        game = make_game()
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
        game.director.state = FIGHT          # Boss 战换 Boss 曲
        game._update_music()
        game.victory = True
        game._update_music()

        self.assertEqual(played, ["title", "stage1", "boss_remilia", "ending"])


class StageFlowTests(unittest.TestCase):
    def test_title_enter_starts_the_stage_intro(self) -> None:
        game = make_game()
        game.scene = Game.SCENE_TITLE

        # 标题 → Enter → 关卡选择
        dispatch_keys(game, pygame.K_RETURN)
        self.assertEqual(game.scene, Game.SCENE_STAGE_SELECT)

        # 关卡选择 → Enter → 进入游戏
        dispatch_keys(game, pygame.K_RETURN)
        self.assertEqual(game.scene, Game.SCENE_PLAYING)
        self.assertEqual(game.director.state, BANNER)
        self.assertIsNotNone(game.director.banner)
        self.assertIsNone(game.boss)          # 关底 Boss 要等波次之后才出场

    def test_banner_freezes_the_battlefield_until_it_fades(self) -> None:
        game = make_game()
        game.director.start()
        self.assertEqual(game.director.state, BANNER)
        boss_position = game.boss.pos.copy()
        player_position = game.player.pos.copy()

        game.update(0.5)

        self.assertAlmostEqual(game.director.timer, 0.5)
        self.assertEqual(game.boss.pos, boss_position)
        self.assertEqual(game.player.pos, player_position)
        self.assertEqual(game.bullets, [])

    def test_title_exit_item_and_escape_close_the_game(self) -> None:
        game = make_game()
        game.scene = Game.SCENE_TITLE
        # 「退出游戏」位于菜单索引 3：从索引 0 向下三次到达
        dispatch_keys(game, pygame.K_DOWN, pygame.K_DOWN, pygame.K_DOWN, pygame.K_RETURN)
        self.assertFalse(game.running)

        game = make_game()
        game.scene = Game.SCENE_TITLE
        dispatch_keys(game, pygame.K_ESCAPE)
        self.assertFalse(game.running)

    def test_gameplay_does_not_advance_while_on_title(self) -> None:
        game = make_game()
        game.scene = Game.SCENE_TITLE
        boss_position = game.boss.pos.copy()

        game.update(1.0)

        self.assertEqual(game.boss.pos, boss_position)
        self.assertEqual(game.bullets, [])

    def test_director_completion_enters_victory(self) -> None:
        game = make_game()
        game.director.completed = True
        game.director.stage_number = config.STAGE_COUNT   # 最终关通关才进结局

        game.update(0.0)

        self.assertTrue(game.victory)

    def test_non_final_stage_completion_returns_to_stage_select(self) -> None:
        game = make_game()
        game.director.completed = True
        game.director.stage_number = 1

        with patch("src.game._save_progress"):
            game.update(0.0)

        self.assertFalse(game.victory)
        self.assertEqual(game.scene, Game.SCENE_STAGE_SELECT)
        self.assertEqual(game.unlocked_stage, 2)

    def test_stage_clear_bonus_is_awarded_once_per_stage(self) -> None:
        game = make_game()
        game.director.cleared_stage = 1

        with patch.object(game, "_read_player_input", return_value=(False, False)):
            game.update(0.0)
            self.assertEqual(game.score, config.STAGE_CLEAR_BONUS)
            self.assertEqual(game.awarded_clear, 1)

            game.update(0.0)                   # 同一关不重复发
            self.assertEqual(game.score, config.STAGE_CLEAR_BONUS)

            game.director.cleared_stage = 2    # 下一关再发一次
            game.update(0.0)

        self.assertEqual(game.score, config.STAGE_CLEAR_BONUS * 2)
        self.assertEqual(game.awarded_clear, 2)


class PlayerControlTests(unittest.TestCase):
    def test_player_is_clamped_to_the_bullet_playfield(self) -> None:
        game = make_game()
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
        game = make_game()

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
        game = make_game()
        game.shooting = True

        game._spawn_player_shots(0.0)
        game._spawn_player_shots(0.1)
        self.assertEqual(len(game.player_shots), 1)

        game._spawn_player_shots(0.1)
        self.assertEqual(len(game.player_shots), 2)

    def test_quick_z_tap_fires_even_if_key_is_released_before_poll(self) -> None:
        game = make_game()
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
        game = make_game()

        class RightAndZ:
            def __getitem__(self, key):
                return key in (pygame.K_RIGHT, pygame.K_z)

        with patch.object(pygame.key, "get_pressed", return_value=RightAndZ()):
            game.focus, game.shooting = game._read_player_input()

        self.assertEqual(game.player.vel.x, config.PLAYER_SPEED)
        self.assertTrue(game.shooting)


class BossSpellTests(unittest.TestCase):
    def test_spawns_use_the_spell_data_bullet_counts(self) -> None:
        game = make_game()

        for emitter in game.boss.spell.emitters:
            before = len(game.bullets)
            game._spawn_boss_attack(game.boss, emitter)
            self.assertEqual(len(game.bullets) - before, emitter.count)

    def test_bullets_spawn_from_the_boss_body_anchor(self) -> None:
        game = make_game()
        origin = game._boss_attack_origin(game.boss)

        game._update_boss_attacks(0.0)

        self.assertTrue(game.bullets)
        self.assertTrue(all(b.pos == origin for b in game.bullets))
        self.assertEqual(
            origin.y,
            game.boss.pos.y + config.BOSS_ATTACK_ORIGIN_OFFSET[1],
        )

    def test_aimed_fan_points_at_the_player(self) -> None:
        game = make_game()

        game._update_boss_attacks(0.0)

        aimed = min(game.bullets, key=lambda bullet: abs(bullet.vel.x))
        self.assertGreater(aimed.vel.y, 0.0)

    def test_spiral_emitter_advances_the_spell_phase(self) -> None:
        game = make_game()
        game.boss.take_damage(game.boss.max_hp * 2.0 / 3.0)   # 第三张：螺旋 + 散射
        spiral = next(
            emitter for emitter in game.boss.spell.emitters
            if emitter.kind == "spiral"
        )

        game._spawn_boss_attack(game.boss, spiral)

        self.assertGreater(game.boss.spell_angle, 0.0)

    def test_emitters_fire_on_their_own_cooldown(self) -> None:
        game = make_game()
        first = game.boss.spell.emitters[0]

        game._update_boss_attacks(0.0)
        self.assertEqual(len(game.bullets), first.count)

        game._update_boss_attacks(first.interval - 0.01)      # 冷却未到
        self.assertEqual(len(game.bullets), first.count)

        game._update_boss_attacks(0.02)                       # 熬过冷却
        self.assertEqual(len(game.bullets), first.count * 2)

    def test_new_spell_resets_the_timer_and_settles_the_previous_one(self) -> None:
        game = make_game()
        game.boss_attack_phase = 1
        game.boss.take_damage(game.boss.max_hp / 3.0)         # 转入第二张

        game._update_boss_attacks(0.0)

        self.assertEqual(game.boss_attack_phase, 2)
        self.assertEqual(game.spells_captured, 1)
        self.assertEqual(game.phase_timer, game.boss.spell.duration)
        self.assertEqual(len(game.items), config.BOSS_PHASE_DROP_POWER)

    def test_timed_out_spell_marks_failure_and_rolls_to_the_next_card(self) -> None:
        game = make_game()
        game.boss_attack_phase = 1
        game.phase_timer = 0.0

        game._update_boss_attacks(0.0)
        self.assertEqual(game.boss.phase, 2)
        self.assertTrue(game.spell_timed_out)

        game._update_boss_attacks(0.0)                        # 下一帧结算
        self.assertEqual(game.spells_failed, 1)
        self.assertEqual(game.spells_captured, 0)

    def test_final_spell_timeout_defeats_the_boss(self) -> None:
        game = make_game()
        segment = game.boss.max_hp / game.boss.spell_count
        game.boss.hp = segment
        game.boss_attack_phase = game.boss.spell_count
        game.phase_timer = 0.0

        game._update_boss_attacks(0.0)

        self.assertEqual(game.boss.hp, 0.0)
        self.assertFalse(game.boss.alive)


class SpellCaptureTests(unittest.TestCase):
    def test_captured_spell_awards_base_and_time_bonus(self) -> None:
        game = make_game()

        game._settle_spell(12.4)

        self.assertEqual(game.spells_captured, 1)
        self.assertEqual(game.spells_failed, 0)
        self.assertEqual(
            game.score,
            config.BOSS_SPELL_BASE_BONUS + config.BOSS_SPELL_TIME_BONUS * 12,
        )

    def test_imperilled_spell_counts_as_failure_without_score(self) -> None:
        game = make_game()
        game.spell_imperilled = True

        game._settle_spell(30.0)

        self.assertEqual(game.spells_captured, 0)
        self.assertEqual(game.spells_failed, 1)
        self.assertEqual(game.score, 0)
        self.assertFalse(game.spell_imperilled)

    def test_being_hit_makes_the_current_spell_uncapturable(self) -> None:
        game = make_game()
        bullet = Bullet(100.0, 100.0, 0.0, 0.0)
        game.bullets = [bullet]

        game._on_player_hit(bullet)

        self.assertTrue(game.spell_imperilled)

    def test_final_hit_settles_the_last_spell_and_reports_to_the_director(self) -> None:
        game = make_game()
        game.boss.hp = config.PLAYER_SHOT_DAMAGE
        game.bullets = [Bullet(100.0, 100.0, 0.0, 100.0)]
        boss_x = config.BOSS_START_X
        shot = PlayerShot(boss_x, config.BOSS_START_Y)
        shot.prev_pos = Vector2(boss_x, config.BOSS_START_Y + 35)
        shot.pos = Vector2(boss_x, config.BOSS_START_Y - 35)
        game.player_shots = [shot]

        game._check_boss_collisions()

        self.assertIsNone(game.boss)
        self.assertEqual(game.bullets, [])
        self.assertEqual(game.player_shots, [])
        self.assertEqual(game.spells_captured, 1)
        self.assertTrue(game.director._boss_defeated)
        self.assertGreaterEqual(game.score, config.VICTORY_SCORE)


class PlayerShotTests(unittest.TestCase):
    def test_player_shot_hits_moving_boss_using_relative_sweep(self) -> None:
        game = make_game()
        game.boss.prev_pos = Vector2(240, 120)
        game.boss.pos = Vector2(250, 120)
        shot = PlayerShot(245, 120)
        shot.prev_pos = Vector2(245, 155)
        shot.pos = Vector2(245, 85)
        game.player_shots = [shot]

        game._check_boss_collisions()

        self.assertEqual(game.boss.hp, game.boss.max_hp - shot.damage)
        self.assertFalse(shot.alive)
        self.assertEqual(game.player_shots, [])

    def test_dead_player_shots_are_removed_after_boss_is_defeated(self) -> None:
        game = make_game()
        game.boss.alive = False
        shot = PlayerShot(100, 0)
        shot.alive = False
        game.player_shots = [shot]

        game._check_boss_collisions()

        self.assertEqual(game.player_shots, [])


class PlayerDamageTests(unittest.TestCase):
    def test_player_hit_consumes_life_clears_bullets_and_respawns(self) -> None:
        game = make_game()
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
        game = make_game()
        game.invulnerable_timer = config.PLAYER_INVULNERABLE_TIME / 2
        bullet = Bullet(game.player.pos.x, game.player.pos.y, 0, 0)
        game.bullets = [bullet]

        game._check_collisions()

        self.assertEqual(game.lives, config.PLAYER_LIVES)
        self.assertEqual(game.hit_total, 0)
        self.assertTrue(bullet.alive)

    def test_god_mode_prevents_bullet_hits_without_spending_lives(self) -> None:
        game = make_game()
        game.god_mode = True
        bullet = Bullet(game.player.pos.x, game.player.pos.y, 0, 0)
        game.bullets = [bullet]

        game._check_collisions()

        self.assertEqual(game.lives, config.PLAYER_LIVES)
        self.assertEqual(game.hit_total, 0)
        self.assertTrue(bullet.alive)
        self.assertFalse(game.game_over)

    def test_invulnerability_timer_counts_down_during_play(self) -> None:
        game = make_game()
        game.invulnerable_timer = config.PLAYER_INVULNERABLE_TIME

        with patch.object(game, "_read_player_input", return_value=(False, False)):
            game.update(0.5)

        self.assertAlmostEqual(
            game.invulnerable_timer,
            config.PLAYER_INVULNERABLE_TIME - 0.5,
        )

    def test_last_life_enters_game_over_and_clears_combat(self) -> None:
        game = make_game()
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

    def test_last_life_persists_a_new_high_score(self) -> None:
        game = make_game()
        game.lives = 1
        game.hiscore = 0
        game.score = 12345

        with patch("src.game._save_hiscore") as save:
            game._on_player_hit(Bullet(200, 200, 0, 100))

        self.assertEqual(game.hiscore, 12345)
        save.assert_called_once_with(12345)

    def test_failure_keeps_an_older_high_score(self) -> None:
        game = make_game()
        game.lives = 1
        game.hiscore = 50000
        game.score = 12345

        with patch("src.game._save_hiscore") as save:
            game._on_player_hit(Bullet(200, 200, 0, 100))

        self.assertEqual(game.hiscore, 50000)
        save.assert_not_called()


class BombTests(unittest.TestCase):
    def test_bomb_clears_nearby_bullets_and_scores(self) -> None:
        game = make_game()
        near = Bullet(game.player.pos.x + 10.0, game.player.pos.y, 0.0, 0.0)
        far = Bullet(
            game.player.pos.x + config.PLAYER_BOMB_RADIUS + 200.0,
            game.player.pos.y, 0.0, 0.0,
        )
        game.bullets = [near, far]

        game._use_bomb()

        self.assertEqual(game.bombs, config.PLAYER_BOMB_START - 1)
        self.assertEqual(game.bullets, [far])
        self.assertEqual(game.score, config.PLAYER_BOMB_BULLET_SCORE)
        self.assertAlmostEqual(game.bomb_timer, config.PLAYER_BOMB_DURATION)
        self.assertTrue(game.spell_imperilled)

    def test_bomb_is_ignored_without_charges(self) -> None:
        game = make_game()
        game.bombs = 0
        game.bullets = [Bullet(game.player.pos.x, game.player.pos.y, 0.0, 0.0)]

        game._use_bomb()

        self.assertEqual(game.bombs, 0)
        self.assertEqual(len(game.bullets), 1)
        self.assertFalse(game.spell_imperilled)


class GameOverAndEndingTests(unittest.TestCase):
    def test_game_over_freezes_the_battlefield(self) -> None:
        game = make_game()
        game.game_over = True
        boss_position = game.boss.pos.copy()

        game.update(1.0)

        self.assertEqual(game.boss.pos, boss_position)
        self.assertEqual(game.bullets, [])

    def test_game_over_r_restarts_a_clean_run(self) -> None:
        game = make_game()
        game.game_over = True
        game.lives = 0
        game.invulnerable_timer = 0.5
        game.boss.take_damage(game.boss.max_hp)

        dispatch_keys(game, pygame.K_r)

        self.assertFalse(game.game_over)
        self.assertFalse(game.victory)
        self.assertEqual(game.scene, Game.SCENE_PLAYING)
        self.assertEqual(game.lives, config.PLAYER_LIVES)
        self.assertEqual(game.invulnerable_timer, 0.0)
        self.assertIsNone(game.boss)              # 新一局从关卡的杂兵波次重新开始
        self.assertEqual(game.director.state, BANNER)

    def test_game_over_enter_and_escape_return_to_title(self) -> None:
        for key in (pygame.K_RETURN, pygame.K_ESCAPE):
            with self.subTest(key=key):
                game = make_game()
                game.game_over = True

                dispatch_keys(game, key)

                self.assertEqual(game.scene, Game.SCENE_TITLE)
                self.assertFalse(game.game_over)
                self.assertTrue(game.running)

    def test_victory_pages_can_be_read_then_closed(self) -> None:
        game = make_game()
        game.victory = True

        dispatch_keys(game, pygame.K_RETURN)
        self.assertEqual(game.ending_page, 1)
        self.assertEqual(game.scene, Game.SCENE_PLAYING)
        dispatch_keys(game, pygame.K_RIGHT)
        self.assertEqual(game.ending_page, 2)
        dispatch_keys(game, pygame.K_LEFT)
        self.assertEqual(game.ending_page, 1)
        dispatch_keys(game, pygame.K_RETURN)
        self.assertEqual(game.ending_page, 2)

        # 翻完所有后记页与谢辞页后，再按 Enter 回到标题
        dispatch_keys(game, pygame.K_RETURN)
        self.assertEqual(game.ending_page, 3)
        dispatch_keys(game, pygame.K_RETURN)
        self.assertEqual(game.ending_page, 4)
        dispatch_keys(game, pygame.K_RETURN)
        self.assertEqual(game.scene, Game.SCENE_TITLE)
        self.assertFalse(game.victory)
        self.assertTrue(game.running)

    def test_victory_escape_returns_to_title_from_any_page(self) -> None:
        game = make_game()
        game.victory = True
        game.ending_page = 1

        dispatch_keys(game, pygame.K_ESCAPE)

        self.assertEqual(game.scene, Game.SCENE_TITLE)
        self.assertFalse(game.victory)


class ResetRunTests(unittest.TestCase):
    def test_reset_run_restores_a_clean_run(self) -> None:
        game = make_game()
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
        game.bombs = 0
        game.invulnerable_timer = 0.8
        game.game_over = True
        game.fire_timer = 0.1
        game.boss_attack_phase = 3
        game.spells_captured = 2
        game.spells_failed = 1
        game.awarded_clear = 2
        game.phase_timer = 1.0

        game._reset_run()

        self.assertIsNone(game.boss)
        self.assertEqual(game.director.state, BANNER)
        self.assertEqual(game.player.pos.x, config.PLAYER_START_X)
        self.assertEqual(game.player.pos.y, config.PLAYER_START_Y)
        self.assertEqual(game.bullets, [])
        self.assertEqual(game.player_shots, [])
        self.assertFalse(game.paused)
        self.assertFalse(game.victory)
        self.assertEqual(game.ending_page, 0)
        self.assertFalse(game.game_over)
        self.assertEqual(game.lives, config.PLAYER_LIVES)
        self.assertEqual(game.bombs, config.PLAYER_BOMB_START)
        self.assertEqual(game.invulnerable_timer, 0.0)
        self.assertEqual(game.graze_total, 0)
        self.assertEqual(game.hit_total, 0)
        self.assertEqual(game.hit_flash, 0.0)
        self.assertEqual(game.fire_timer, 0.0)
        self.assertEqual(game.boss_attack_phase, 0)
        self.assertEqual(game.spell_timers, [])
        self.assertEqual(game.spells_captured, 0)
        self.assertEqual(game.spells_failed, 0)
        self.assertEqual(game.awarded_clear, 0)
        self.assertEqual(game.phase_timer, config.BOSS_PHASE_TIME_LIMIT)
        self.assertEqual(game.score, 0)


if __name__ == "__main__":
    unittest.main()
