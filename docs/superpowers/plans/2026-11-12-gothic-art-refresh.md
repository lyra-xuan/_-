# Gothic Art Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the prototype battle presentation with a dark, gothic Touhou 6 art direction while retaining the 1280x960 window and custom collision logic.

**Architecture:** Keep the screen divided into a left bullet-playfield and a right HUD, following the reference game's proportions. Copy only the needed user-provided Touhou assets into the repository, combine their grayscale alpha masks at load time, and pass prepared images to the existing entities for rendering. Keep collision radii independent from sprite dimensions.

**Tech Stack:** Python 3.12, pygame-ce, unittest, PNG/JPEG source art.

---

### Task 1: Vendor the selected Touhou art

**Files:**
- Create: `assets/gameplay/`
- Create: `assets/gameplay/ATTRIBUTION.md`
- Source: user's `东方原作弹幕游戏素材包/东方Project游戏开源素材库/TH06 东方红魔乡`

- [x] Copy `TL_DAT/select00.jpg`, `ST_DAT/stg6bg.png`, `CM_DAT/player00.png`, `CM_DAT/player00_a.png`, `CM_DAT/etama3.png`, `CM_DAT/etama3_a.png`, `ST_DAT/face12a.png`, and `ST_DAT/face12a_a.png` into `assets/gameplay/`.
- [x] Record the source paths, copyright notices, and the user's stated permission in `assets/gameplay/ATTRIBUTION.md`.
- [x] Verify the copied files are readable with `pygame.image.load` and that each color/mask pair has matching dimensions.

### Task 2: Define a framed bullet playfield

**Files:**
- Modify: `src/config.py`
- Modify: `src/entities.py`
- Modify: `src/game.py`
- Test: `tests/test_boss_combat.py`
- Test: `tests/test_boss_entities.py`

- [x] Add a 768x896 playfield at `(32, 32)` and derive player spawn, Boss spawn, and Boss horizontal bounds from it.
- [x] Clamp player movement and remove off-screen enemy bullets against playfield bounds rather than the entire window.
- [x] Test that the player remains inside the playfield and the Boss bounces within its horizontal bounds.
- [x] Keep the spatial grid and all swept collision calculations in world coordinates.

### Task 3: Prepare Touhou sprites and replace prototype entities

**Files:**
- Create: `src/art.py`
- Modify: `src/entities.py`
- Modify: `src/game.py`
- Test: `tests/test_boss_combat.py`

- [x] Add an asset loader that alpha-composites the supplied mask images and exposes the mansion background, two Reimu animation frames, a Boss portrait, enemy bullets, and player shots.
- [x] Extend `Player.draw`, `Boss.draw`, `Bullet.draw`, and `PlayerShot.draw` with optional image parameters while preserving the existing collision radii.
- [x] Pass the loaded images from `Game` and remove the normal-play geometric circles that currently stand in for the player and Boss.
- [x] Test image loading and confirm drawing does not mutate entity positions or collision radii.

### Task 4: Restyle battle layout and update documentation

**Files:**
- Modify: `src/game.py`
- Modify: `src/config.py`
- Modify: `README.md`
- Modify: `docs/requirements.md`
- Modify: `docs/assets.md`
- Test: `tests/test_boss_combat.py`

- [x] Draw the user-provided dark mansion and lunar scene art behind the playfield, with a restrained black/crimson/gold HUD on the right.
- [x] Show Boss portrait and health, lives, graze/hit counts, bullet count, and key hints in the sidebar.
- [x] Keep the title-screen asset treatment intact and update the gameplay screenshots/asset notes if needed.
- [x] Run `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` and render the title, battle, and failure states at 1280x960.
- [x] Commit the completed visual refresh after tests pass.
