# Boss Victory Afterword and Credits Implementation Plan

> **Execution record:** Completed inline. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Extend the Boss victory screen with an in-world afterword and a final acknowledgments page using the existing Touhou-style result artwork.

**Architecture:** Keep defeat screens unchanged. Model the victory ending as three pages in the existing `Game` scene: the current score summary, a short epilogue, and credits. Use explicit ending-page state and keyboard navigation; use `ED_DAT/end01.jpg` behind the afterword, `ED_DAT/staff00.jpg` behind acknowledgments, and the PC-98 ending theme `Peaceful Romancer` as victory music.

**Tech Stack:** Python 3.14, pygame-ce, unittest.

---

### Task 1: Add victory-page navigation

**Files:**
- Modify: `src/game.py`
- Modify: `src/art.py`
- Modify: `src/audio.py`
- Add: `assets/gameplay/ending-afterword.jpg`
- Add: `assets/gameplay/ending-credits.jpg`
- Add: `assets/bgm/ending.ogg`
- Modify: `assets/gameplay/ATTRIBUTION.md`
- Modify: `assets/bgm/ATTRIBUTION.md`
- Test: `tests/test_boss_combat.py`

- [x] **Step 1: Implement victory-page state and key handling**

- [x] **Step 2: Add and run navigation tests**

Test that victory starts on page 0, Enter or Right advances through pages 1 and 2, Left moves back, R restarts, and Esc returns to the title. Enter on page 2 also returns to the title.

Run: `python -m unittest tests.test_boss_combat`

Expected: all victory navigation tests pass.

- [x] **Step 3: Verify the complete regression suite**

Run: `python -m unittest discover -s tests`

Expected: all tests pass.

### Task 2: Render the afterword and acknowledgments

**Files:**
- Modify: `src/game.py`
- Test: `tests/test_boss_combat.py`

- [x] **Step 1: Add content assertions**

Assert that the afterword contains the red mist, Remilia, and the incident being resolved, and that the last page contains both the material/music credits and a direct thank-you to the player.

- [x] **Step 2: Add Japanese-style page content**

Use these afterword lines, broken to fit the left text column:

```text
紅霧散去，滿月重新照亮了湖面。
蕾米莉亞仍說，這不過是一場稍有趣味的遊戲。
咲夜默默收拾彈痕與碎裂的窗玻璃，
又替主人端來一杯溫熱的紅茶。

博麗的巫女沒有收下謝禮，只確認人里的燈火
已重新亮起，便乘風回到神社。

數日之後，紅魔館再度傳出彈幕的聲響。
幻想鄉的異変，大概從來不曾真正完結。
```

The credits page lists the original work, `Peaceful Romancer` by ZUN, the TH06 original asset source, and creator `lyra`. The closing line thanks the player:

```text
そして、最後まで遊んでくれた貴方へ。
ありがとう。
```

- [x] **Step 2: Register original assets and ending music**

Copy the original TH06 `ED_DAT/end01.jpg` and `ED_DAT/staff00.jpg` into the gameplay asset directory and credit them. Convert the user-provided TH05 FM86 `Peaceful Romancer.flac` to `assets/bgm/ending.ogg` with an audio-only Vorbis encode; add it to the music map and credit table.

- [x] **Step 3: Implement page rendering**

Keep page 0 as the current result summary. Render pages 1 and 2 inside the existing double-line gold panel over their corresponding original full-screen images, use `後記 / POST-SCRIPT` and `謝辞 / CREDITS` headings, and add page-specific navigation hints in the footer.

- [x] **Step 4: Verify the content and screen navigation tests**

Run: `python -m unittest tests.test_boss_combat`

Expected: content, navigation, restart, and title-return assertions all pass.

### Task 3: Update player-facing instructions and run the full suite

**Files:**
- Modify: `README.md`
- Modify: `docs/requirements.md`
- Modify: `docs/assets.md`
- Modify: `src/game.py`
- Test: `tests/test_boss_combat.py`

- [x] **Step 1: Update instructions**

Document victory-page controls: Left/Right or Enter to read, R to replay, and Esc to return to the title. Keep defeat-screen controls unchanged, and document the original ending artwork and `Peaceful Romancer` music credits.

- [x] **Step 2: Run all tests and check whitespace**

Run: `python -m unittest discover -s tests`

Expected: all tests pass.

Run: `git diff --check`

Expected: no whitespace errors.
