# Boss Battle Prototype Implementation Plan

> **For agentic workers:** Use this plan task-by-task. Each step has a pre-work and completion checklist.

**Goal:** Add a playable one-boss prototype with player shots, two boss attack phases, health feedback, and a victory/restart loop.

**Architecture:** Keep movement and health in entities, combat timing and collision in `Game`, and draw all visuals with pygame primitives. Use relative-motion segment-circle collision for player shots against the moving boss.

**Tech Stack:** Python 3.12, pygame-ce, `unittest`.

## File Map

- Modify `src/config.py`: centralize boss, player-shot, and firing parameters.
- Modify `src/entities.py`: add `PlayerShot` and `Boss`.
- Modify `src/game.py`: own combat entities, input, attack patterns, hit handling, victory/restart, and HUD.
- Create `tests/test_boss_entities.py`: test movement, health phases, and player-shot lifecycle.
- Create `tests/test_boss_combat.py`: test shot collision, boss phase patterns, and victory/restart.
- Modify `README.md` and `docs/requirements.md`: update controls and delivered scope.

## Task 1: Combat Entities

**Before checklist**

- [x] Keep the existing `Entity.update(dt)` contract.
- [x] Add boss bounds, horizontal speed, radius, and maximum HP to config.
- [x] Add player-shot speed, radius, and damage to config.
- [x] Test boss bounce, half-HP phase transition, and upward/offscreen player-shot behavior.

**Implementation contract**

- `Boss(x, y)` exposes `hp`, `max_hp`, `direction`, `phase`, `prev_pos`, and `take_damage(amount)`.
- Boss movement stays between `BOSS_LEFT_BOUND` and `BOSS_RIGHT_BOUND`; `phase` becomes 2 at or below half HP.
- `PlayerShot(x, y)` moves upward, records `prev_pos`, and becomes dead after leaving the top margin.
- Both entities implement `draw(surface)` using pygame primitives only.

**Verify:** `python -m unittest tests.test_boss_entities -v`

**Completion checklist**

- [x] Added `Boss` and `PlayerShot` with program-drawn visuals.
- [x] All four entity tests and both existing collision tests pass.
- [x] Committed as `81beed7`.

## Task 2: Combat Integration

**Before checklist**

- [x] Add a held-Z firing timer and player-shot collection to `Game`.
- [x] Replace random top-edge spawning with attacks emitted from the boss.
- [x] Phase 1 fires a five-shot aimed fan every 0.85 seconds.
- [x] Phase 2 fires an eight-direction ring every 0.60 seconds.
- [x] Resolve player shots against the boss using relative-motion `segment_circle`.
- [x] Preserve existing player/enemy-bullet hit and graze behavior.

**Verify:** `python -m unittest tests.test_boss_combat -v`

**Completion checklist**

- [x] Added firing-interval, relative-motion hit, phase-timing, and defeated-Boss cleanup tests.
- [x] All 12 tests pass.
- [x] Independent review found and the implementation fixed phase-timer and projectile-cleanup issues.
- [ ] Boss/player-shot drawing and victory feedback remain in Task 3.

## Task 3: Feedback and Regression

**Before checklist**

- [ ] Draw the boss, player shots, boss HP bar, and current phase.
- [ ] Stop combat updates after victory and show a restart prompt.
- [ ] Restart restores player, boss HP, timers, counters, and all projectile lists.
- [ ] Update README controls and requirements status.
- [ ] Run `python -m unittest discover -s tests -v` and `python -m compileall -q src tests main.py`.
- [ ] Inspect the final diff, commit the completed feature, and report whether remote push is pending.

**Acceptance:** Player can hold Z to defeat the boss; the boss visibly changes attack at half HP; the victory screen can restart a fresh run; all tests pass.
