"""剧情对话：立绘 + 对话框。

贴近原作的一来一回：每一行指定说话者（据此取出对应立绘）、表情序号与站位，
正文按打字机速度逐字浮现，按 Z / Enter 先补全当前行、再推进到下一行。
"""
from __future__ import annotations

from dataclasses import dataclass

import pygame

from . import config

# 角色键 -> 显示名；与 art.portraits 的键一一对应
SPEAKER_NAMES = {
    "reimu": "博丽灵梦",
    "rumia": "露米娅",
    "cirno": "琪露诺",
    "meiling": "红美铃",
    "patchouli": "帕秋莉·诺蕾姬",
    "sakuya": "十六夜咲夜",
    "remilia": "蕾米莉亚·史卡雷特",
}

CHARS_PER_SECOND = 46.0     # 打字机速度
PORTRAIT_CLEARANCE = 316    # 正文为立绘让出的横向宽度


@dataclass(frozen=True)
class Line:
    """一行台词。"""

    speaker: str
    text: str
    expression: int = 0     # 立绘表情序号，超出范围时回退到最后一张
    side: str = "left"      # 立绘站位：left / right

    @property
    def name(self) -> str:
        return SPEAKER_NAMES.get(self.speaker, self.speaker)


@dataclass(frozen=True)
class Scene:
    """一场对话。"""

    lines: tuple[Line, ...]
    title: str = ""


def _wrap(text: str, width: int) -> tuple[str, ...]:
    """按显示宽度折行；正文以中日文为主，按字符数切分即可。"""
    if width <= 0:
        return (text,)
    return tuple(text[i:i + width] for i in range(0, len(text), width)) or ("",)


class DialogueBox:
    """一场对话的播放状态（当前行、打字机进度）。"""

    def __init__(self, scene: Scene) -> None:
        self.scene = scene
        self.index = 0
        self.timer = 0.0

    @property
    def lines(self) -> tuple[Line, ...]:
        return self.scene.lines

    @property
    def finished(self) -> bool:
        return self.index >= len(self.scene.lines)

    @property
    def line(self) -> Line | None:
        if self.finished:
            return None
        return self.scene.lines[self.index]

    @property
    def reveal(self) -> bool:
        """当前行是否已经完整显示（决定按键是补全还是翻页）。"""
        line = self.line
        if line is None:
            return True
        return self.timer * CHARS_PER_SECOND >= len(line.text)

    def visible_text(self) -> str:
        line = self.line
        if line is None:
            return ""
        count = int(self.timer * CHARS_PER_SECOND)
        return line.text if count >= len(line.text) else line.text[:count]

    def update(self, dt: float) -> None:
        self.timer += dt

    def advance(self) -> bool:
        """推进对话；返回 ``True`` 表示整场对话结束。"""
        line = self.line
        if line is not None and not self.reveal:
            self.timer = len(line.text) / CHARS_PER_SECOND    # 先补全本行
            return False
        self.index += 1
        self.timer = 0.0
        return self.finished

    # ------------------------------------------------------------------ #
    # 渲染
    # ------------------------------------------------------------------ #
    def draw(self, surface: pygame.Surface, art, font: pygame.font.Font,
             font_big: pygame.font.Font) -> None:
        line = self.line
        if line is None:
            return

        field = pygame.Rect(
            config.PLAYFIELD_LEFT, config.PLAYFIELD_TOP,
            config.PLAYFIELD_WIDTH, config.PLAYFIELD_HEIGHT,
        )
        shade = pygame.Surface(field.size, pygame.SRCALPHA)
        shade.fill((6, 3, 9, 132))
        surface.blit(shade, field.topleft)

        box = pygame.Rect(field.left + 14, field.bottom - 286,
                          field.width - 28, 268)
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        panel.fill((10, 5, 12, 240))
        surface.blit(panel, box.topleft)
        pygame.draw.rect(surface, config.GOLD, box, 2)
        pygame.draw.rect(surface, (120, 68, 54), box.inflate(-12, -12), 1)

        frames = art.portraits.get(line.speaker) or ()
        if frames:
            portrait = frames[min(line.expression, len(frames) - 1)]
            anchor = (box.left + 16 if line.side == "left" else box.right - 16)
            rect = portrait.get_rect(bottom=box.top + 30)
            if line.side == "left":
                rect.left = anchor
            else:
                rect.right = anchor
            surface.blit(portrait, rect)

        # 名牌贴在对话框上沿，压在立绘与正文之间
        name_surface = font.render(line.name, True, config.PALE_GOLD)
        plate = name_surface.get_rect()
        plate.width += 28
        plate.height += 14
        plate.topleft = (box.left + 20, box.top - plate.height // 2)
        plate_back = pygame.Surface(plate.size, pygame.SRCALPHA)
        plate_back.fill((26, 10, 18, 244))
        surface.blit(plate_back, plate.topleft)
        pygame.draw.rect(surface, config.GOLD, plate, 1)
        surface.blit(name_surface, name_surface.get_rect(center=plate.center))

        if line.side == "left":
            text_left, text_right = box.left + PORTRAIT_CLEARANCE, box.right - 28
        else:
            text_left, text_right = box.left + 28, box.right - PORTRAIT_CLEARANCE
        width = max(6, (text_right - text_left) // max(1, font.size("字")[0]))
        y = box.top + 48
        for row in _wrap(self.visible_text(), width):
            surface.blit(font.render(row, True, config.WHITE), (text_left, y))
            y += 36

        if not self.scene.title:
            return
        title = font_big.render(self.scene.title, True, config.MUTED)
        title.set_alpha(180)
        surface.blit(title, (box.left + 20, field.top + 16))
