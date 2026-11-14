"""音效与背景音乐播放。

音效来自 TH06 的 ``IN_DAT``（见 ``assets/audio/ATTRIBUTION.md``）；背景音乐
由 PC-98 时期东方原曲转码而来（见 ``assets/bgm/ATTRIBUTION.md``）。

音频设备可能不存在（无声卡、CI 环境），因此加载与初始化失败一律静默降级为
静音，绝不让音频问题影响游戏逻辑与测试。
"""
from __future__ import annotations

from pathlib import Path

import pygame

_AUDIO_ROOT = Path(__file__).resolve().parent.parent / "assets" / "audio"
_BGM_ROOT = Path(__file__).resolve().parent.parent / "assets" / "bgm"

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

# 场景 -> 背景音乐文件列表（按优先级尝试，第一个能加载的为准）
# TH06 原作 MIDI 优先；旧版 PC-98 OGG 作为降级。
_MUSIC_FILES: dict[str, list[str]] = {
    "title": ["title.mid", "title.ogg"],
    "stage_select": ["stage-select.mid", "title.ogg"],
    "stage1": ["stage1.mid", "stage.ogg"],
    "stage2": ["stage2.mid", "stage.ogg"],
    "stage3": ["stage3.mid", "stage.ogg"],
    "boss_rumia": ["boss-rumia.mid", "boss.ogg"],
    "boss_cirno": ["boss-cirno.mid", "boss.ogg"],
    "boss_remilia": ["boss-remilia.mid", "boss.ogg"],
    "boss_sakuya": ["boss-sakuya.mid", "boss.ogg"],
    "ceremony": ["ceremony.mid", "boss.ogg"],
    "ending": ["ending.mid", "ending.ogg"],
    "credits": ["credits.mid", "ending.ogg"],
}

_MUSIC_VOLUME = 0.5


class Audio:
    """按名字播放音效与循环背景音乐；任何环节失败都只是少一段声音。"""

    def __init__(self) -> None:
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.music_ready = False        # 混音器可用且 music 通道可用
        self.current_music: str | None = None
        self._missing_music: set[str] = set()
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except pygame.error:
            return          # 无音频设备：整体静音

        self.music_ready = True
        for name, filename in _SOUND_FILES.items():
            try:
                self.sounds[name] = pygame.mixer.Sound(str(_AUDIO_ROOT / filename))
            except (pygame.error, OSError):
                continue

    def play(self, name: str) -> None:
        sound = self.sounds.get(name)
        if sound is not None:
            sound.play()

    def play_music(self, name: str, fade_ms: int = 600) -> None:
        """循环播放指定背景音乐；已在播放同一首时不重启。

        每个逻辑名对应一个候选文件列表，按顺序尝试，第一个能成功加载
        的文件即被使用（TH06 原作 MIDI 优先，PC-98 OGG 作降级）。
        """
        if not self.music_ready or name == self.current_music:
            return
        if name in self._missing_music:
            return
        candidates = _MUSIC_FILES.get(name, [])
        path: Path | None = None
        for filename in candidates:
            candidate = _BGM_ROOT / filename
            if candidate.is_file():
                path = candidate
                break
        if path is None:
            self._missing_music.add(name)   # 全部缺失，避免每帧重复查盘
            return
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(_MUSIC_VOLUME)
            pygame.mixer.music.play(-1, fade_ms=fade_ms)
        except pygame.error:
            # 单个文件解码失败：尝试下一个候选；全部失败则标记此逻辑名不可用
            idx = candidates.index(path.name) if path.name in candidates else 0
            remaining = candidates[idx + 1:]
            for filename in remaining:
                candidate = _BGM_ROOT / filename
                if not candidate.is_file():
                    continue
                try:
                    pygame.mixer.music.load(str(candidate))
                    pygame.mixer.music.set_volume(_MUSIC_VOLUME)
                    pygame.mixer.music.play(-1, fade_ms=fade_ms)
                    path = candidate
                    break
                except pygame.error:
                    continue
            else:
                self._missing_music.add(name)
                return
        self.current_music = name

    def stop_music(self, fade_ms: int = 400) -> None:
        """淡出并停止背景音乐。"""
        if not self.music_ready or self.current_music is None:
            return
        try:
            pygame.mixer.music.fadeout(fade_ms)
        except pygame.error:
            pass
        self.current_music = None
