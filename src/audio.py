"""音效播放。

素材来自 TH06 的 ``IN_DAT``（见 ``assets/audio/ATTRIBUTION.md``）。音频设备
可能不存在（无声卡、CI 环境），因此加载与初始化失败一律静默降级为静音，
绝不让音频问题影响游戏逻辑与测试。
"""
from __future__ import annotations

from pathlib import Path

import pygame

_AUDIO_ROOT = Path(__file__).resolve().parent.parent / "assets" / "audio"

# 逻辑名 -> 文件名；逻辑名供游戏代码引用，避免到处写文件名
_SOUND_FILES = {
    "shot": "player-shot.wav",
    "enemy_hit": "enemy-hit.wav",
    "graze": "graze.wav",
    "alert": "boss-alert.wav",
    "player_dead": "player-dead.wav",
    "enemy_dead": "enemy-dead.wav",
    "phase_change": "phase-change.wav",
    "menu_move": "menu-move.wav",
    "menu_ok": "menu-ok.wav",
    "menu_cancel": "menu-cancel.wav",
}


class Audio:
    """按名字播放音效；任何环节失败都只是少一个音效。"""

    def __init__(self) -> None:
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except pygame.error:
            return          # 无音频设备：整体静音

        for name, filename in _SOUND_FILES.items():
            try:
                self.sounds[name] = pygame.mixer.Sound(str(_AUDIO_ROOT / filename))
            except (pygame.error, OSError):
                continue

    def play(self, name: str) -> None:
        sound = self.sounds.get(name)
        if sound is not None:
            sound.play()
