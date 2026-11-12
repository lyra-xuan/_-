"""Load the licensed Touhou 6 artwork used by the game scenes."""
from __future__ import annotations

from pathlib import Path

import pygame

from . import config


class GameArt:
    """Prepared scene backgrounds and masked sprite images."""

    def __init__(self) -> None:
        root = Path(__file__).resolve().parent.parent / "assets" / "gameplay"
        self.scene_background = pygame.transform.smoothscale(
            pygame.image.load(str(root / "scarlet-mansion.jpg")),
            (config.SCREEN_W, config.SCREEN_H),
        )
        self.playfield_background = pygame.transform.smoothscale(
            pygame.image.load(str(root / "scarlet-moon.png")),
            (config.PLAYFIELD_WIDTH, config.PLAYFIELD_HEIGHT),
        )

        player_frames = (
            pygame.Rect(0, 0, 32, 48),
            pygame.Rect(32, 0, 32, 48),
        )
        self.player_frames = tuple(
            pygame.transform.smoothscale(
                self._load_masked(
                    root / "reimu-sheet.png",
                    root / "reimu-mask.png",
                    rect,
                ),
                (config.PLAYER_SPRITE_WIDTH, config.PLAYER_SPRITE_HEIGHT),
            )
            for rect in player_frames
        )
        self.player_icon = pygame.transform.smoothscale(
            self.player_frames[0], (24, 48)
        )
        self.boss_portrait = pygame.transform.smoothscale(
            self._load_masked(
                root / "boss-portrait.png",
                root / "boss-mask.png",
                pygame.Rect(12, 5, 236, 251),
            ),
            (112, 120),
        )
        self.enemy_bullet_sprites = {
            config.RED: pygame.transform.smoothscale(
                self._load_masked(
                    root / "bullet-sheet.png",
                    root / "bullet-mask.png",
                    pygame.Rect(16, 48, 16, 16),
                ),
                (18, 18),
            ),
            config.CYAN: pygame.transform.smoothscale(
                self._load_masked(
                    root / "bullet-sheet.png",
                    root / "bullet-mask.png",
                    pygame.Rect(112, 48, 16, 16),
                ),
                (18, 18),
            ),
        }
        self.player_shot = pygame.transform.smoothscale(
            self._load_masked(
                root / "bullet-sheet.png",
                root / "bullet-mask.png",
                pygame.Rect(112, 48, 16, 16),
            ),
            (12, 26),
        )

    @staticmethod
    def _load_masked(
            image_path: Path, mask_path: Path,
            rect: pygame.Rect) -> pygame.Surface:
        sheet = pygame.image.load(str(image_path))
        mask_sheet = pygame.image.load(str(mask_path))
        if sheet.get_size() != mask_sheet.get_size():
            raise ValueError(f"Artwork and mask dimensions differ: {image_path}")

        image = sheet.subsurface(rect).copy()
        mask = mask_sheet.subsurface(rect)
        result = pygame.Surface(rect.size, pygame.SRCALPHA, 32)
        for y in range(rect.height):
            for x in range(rect.width):
                color = image.get_at((x, y))
                result.set_at(
                    (x, y),
                    (color.r, color.g, color.b, mask.get_at((x, y)).r),
                )
        return result
