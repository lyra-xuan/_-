# Continuous Collision Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent broad-phase grid filtering and player movement from hiding real hit or graze collisions.

**Architecture:** Store the player's previous position, detect bullet/player contact using relative motion, and expand the endpoint grid query by the maximum relative frame displacement and each bullet's actual radius. Add standard-library `unittest` regressions without adding dependencies.

**Tech Stack:** Python 3.12, pygame-ce, unittest.

---

### Task 1: Add failing collision regressions

**Files:**
- Create: `tests/test_collision_sweeps.py`

- [ ] **Step 1: Add regression tests**

```python
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
```

- [ ] **Step 2: Run regressions before implementation**

Run: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`
Expected: both tests fail against the current implementation.

### Task 2: Implement relative-motion collision and complete broad phase

**Files:**
- Modify: `src/entities.py`
- Modify: `src/game.py`

- [ ] **Step 1: Track the player's previous position**

Initialize `Player.prev_pos` from its starting position and update it before movement:

```python
class Player(Entity):
    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y)
        self.prev_pos = Vector2(self.pos)
        self.radius = config.PLAYER_HIT_RADIUS
        self.graze_radius = config.PLAYER_GRAZE_RADIUS
        self.graze_count = 0

    def update(self, dt: float) -> None:
        self.prev_pos = Vector2(self.pos)
        super().update(dt)
```

- [ ] **Step 2: Expand candidate query and test relative trajectories**

While inserting bullets, track the largest bullet radius plus its frame displacement. Query using that extent plus the player's frame displacement, then test relative bullet/player endpoints:

```python
max_bullet_reach = 0.0
for bullet in self.bullets:
    self.grid.insert(bullet, bullet.pos.x, bullet.pos.y)
    travel = bullet.pos.distance_to(bullet.prev_pos)
    max_bullet_reach = max(max_bullet_reach, bullet.radius + travel)

player_travel = self.player.pos.distance_to(self.player.prev_pos)
query_radius = self.player.graze_radius + player_travel + max_bullet_reach
candidates = self.grid.query(px, py, query_radius)
```

For each candidate, define the relative segment from `bullet.prev_pos - player.prev_pos` to `bullet.pos - player.pos`, and call `segment_circle` against `(0, 0)` with the sum of the applicable radii.

### Task 3: Verify, commit, and independently review

**Files:**
- Test: `tests/test_collision_sweeps.py`
- Verify: `src/entities.py`, `src/game.py`

- [ ] **Step 1: Run regression suite and syntax checks**

Run: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`
Expected: both collision regression tests pass.

Run: `.\.venv\Scripts\python.exe -m compileall -q main.py src tests`
Expected: exit code 0.

- [ ] **Step 2: Commit the completed fix**

```powershell
git add src/entities.py src/game.py tests/test_collision_sweeps.py docs/superpowers/plans/2026-11-12-continuous-collision.md
git commit -m "fix: account for relative motion in collision sweeps"
```

- [ ] **Step 3: Review the commit with an independent read-only agent**

Review `git show HEAD` for correctness, regression coverage, and accidental unrelated changes. Do not modify files during review.
