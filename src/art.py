"""加载已获许可的东方红魔乡素材。

素材以「图像 + 灰度遮罩」两张 PNG 成对存放，遮罩的红通道即 alpha，需要在
载入时合成。所有帧坐标都是对图集实测得到的，集中登记在下面的清单里，
渲染代码只按名字取用，避免坐标散落各处。
"""
from __future__ import annotations

from pathlib import Path

import pygame

from . import config

_ASSET_ROOT = Path(__file__).resolve().parent.parent / "assets" / "gameplay"

# --------------------------------------------------------------------------- #
# 帧清单：格式 (x, y, w, h)，单位像素
# --------------------------------------------------------------------------- #
# 自机（player00）：上排 4 帧直立，下排左倾与右倾各 3 帧。
PLAYER_FRAME_RECTS: dict[str, tuple[tuple[int, int, int, int], ...]] = {
    "idle": ((3, 5, 23, 43), (35, 6, 22, 42), (68, 6, 23, 41), (100, 5, 25, 43)),
    "left": ((3, 53, 22, 41), (36, 54, 23, 42), (71, 54, 21, 41)),
    "right": ((136, 53, 23, 43), (168, 53, 22, 43), (200, 53, 22, 43)),
}
PLAYER_RENDER_SIZE = (config.PLAYER_SPRITE_WIDTH, config.PLAYER_SPRITE_HEIGHT)
PLAYER_ICON_SIZE = (24, 45)

# 大玉（etama3）：y=129 一行 8 色，30×30，x 从 1 起、列距 32。
_LARGE_COLORS = (
    "white", "red", "magenta", "purple", "cyan", "green", "yellow", "gray",
)
BULLET_LARGE_RECTS = {
    name: (1 + index * 32, 129, 30, 30)
    for index, name in enumerate(_LARGE_COLORS)
}
BULLET_LARGE_RENDER = (34, 34)

# 米弹（etama3）：玩家射击使用直线型弹。
BULLET_RICE_RECT = (103, 160, 17, 32)
PLAYER_SHOT_RENDER = (14, 30)

# 小玉（etama4）：y=241 一行 4 色，13×13，列距 64。
BULLET_SMALL_RECTS = {
    "white": (50, 241, 13, 13),
    "red": (114, 241, 13, 13),
    "green": (178, 241, 13, 13),
    "blue": (242, 241, 13, 13),
}
BULLET_SMALL_RENDER = (18, 18)

# 中玉（etama4）。
BULLET_MID_RECTS = {
    "white": (65, 209, 30, 30),
    "red": (97, 209, 30, 30),
    "green": (130, 209, 29, 29),
}
BULLET_MID_RENDER = (26, 26)

# 掉落道具：复用原作弹型贴图，并叠加短标签，避免小尺寸下只像普通弹珠
ITEM_RENDER = (38, 38)
ITEM_LABELS = {"power": "PWR", "point": "PTS", "life": "1UP"}

# 特效（eff00，自带 alpha，无需遮罩）。
EFFECT_SPARK_RECT = (1, 1, 30, 30)      # 命中火花
EFFECT_RING_RECT = (49, 49, 15, 14)     # 擦弹光环
EFFECT_BURST_RECT = (3, 192, 61, 63)    # 击破爆散
EFFECT_SPARK_SIZE = (44, 44)
EFFECT_RING_SIZE = (34, 32)
EFFECT_BURST_SIZE = (168, 174)

# 妖精（stg1enm）：8 列网格，左上 4 帧为小型妖精。
FAIRY_RECTS = ((5, 5, 23, 24), (35, 5, 26, 24), (69, 5, 24, 24), (101, 5, 24, 24))
FAIRY_RENDER = (40, 42)
FAIRY_VARIANT_RECTS = (
    (1, 2, 31, 45), (33, 2, 30, 45), (65, 2, 30, 45),
    (97, 2, 30, 45), (129, 2, 30, 45),
)
FAIRY_VARIANT_RENDER = (38, 52)

# Boss 立绘（face12a / face12c / face10a）。
BOSS_FACE_RECTS = ((4, 0, 252, 256), (4, 0, 248, 256), (0, 0, 256, 256))
BOSS_FACE_RENDER = (176, 178)

# 关卡背景（stg4bg）：图集内有效区域。
STAGE_BG_RECT = (15, 15, 241, 210)


def _compose(
    sheet: pygame.Surface, mask: pygame.Surface, rect: tuple[int, int, int, int],
) -> pygame.Surface:
    """按矩形裁剪并用遮罩红通道合成 alpha。

    只遍历目标帧的像素；python 逐像素循环对整张 256×256 图集太慢，
    按帧裁剪后总量可控。
    """
    x, y, width, height = rect
    source = sheet.subsurface((x, y, width, height))
    alpha = mask.subsurface((x, y, width, height))
    result = pygame.Surface((width, height), pygame.SRCALPHA, 32)
    result.blit(source, (0, 0))
    for row in range(height):
        for column in range(width):
            red, green, blue, _ = result.get_at((column, row))
            result.set_at((column, row), (red, green, blue, alpha.get_at((column, row)).r))
    return result


def _scale_cover(surface: pygame.Surface,
                 size: tuple[int, int]) -> pygame.Surface:
    """等比放大到铺满目标尺寸后居中裁剪，避免直接拉伸变形。"""
    target_w, target_h = size
    source_w, source_h = surface.get_size()
    factor = max(target_w / source_w, target_h / source_h)
    scaled = pygame.transform.smoothscale(
        surface, (max(1, round(source_w * factor)), max(1, round(source_h * factor)))
    )
    rect = pygame.Rect(0, 0, target_w, target_h)
    rect.center = scaled.get_rect().center
    return scaled.subsurface(rect).copy()


class GameArt:
    """整场游戏用到的背景、角色、弹幕与特效贴图。"""

    def __init__(self) -> None:
        sheets: dict[str, pygame.Surface] = {}

        def sheet(name: str) -> pygame.Surface:
            surface = sheets.get(name)
            if surface is None:
                surface = pygame.image.load(str(_ASSET_ROOT / name))
                sheets[name] = surface
            return surface

        def frames(image_name: str, mask_name: str,
                   rects) -> tuple[pygame.Surface, ...]:
            image = sheet(image_name)
            mask = sheet(mask_name)
            return tuple(_compose(image, mask, rect) for rect in rects)

        # ---------------- 场景背景 ----------------
        self.scene_background = pygame.transform.smoothscale(
            sheet("scarlet-mansion.jpg"), (config.SCREEN_W, config.SCREEN_H)
        )
        stage_bg = _compose(sheet("stage-bg.png"), sheet("stage-bg-mask.png"),
                            STAGE_BG_RECT)
        self.playfield_background = _scale_cover(
            stage_bg, (config.PLAYFIELD_WIDTH, config.PLAYFIELD_HEIGHT)
        )
        self.ending_victory = pygame.transform.smoothscale(
            sheet("ending-victory.jpg"), (config.SCREEN_W, config.SCREEN_H)
        )
        self.ending_defeat = pygame.transform.smoothscale(
            sheet("ending-defeat.jpg"), (config.SCREEN_W, config.SCREEN_H)
        )
        self.ending_afterword = pygame.transform.smoothscale(
            sheet("ending-afterword.jpg"), (config.SCREEN_W, config.SCREEN_H)
        )
        self.ending_credits = pygame.transform.smoothscale(
            sheet("ending-credits.jpg"), (config.SCREEN_W, config.SCREEN_H)
        )
        self.result_screen = pygame.transform.smoothscale(
            sheet("result-screen.jpg"), (360, 270)
        )

        # ---------------- 自机 ----------------
        self.player_frames = tuple(
            pygame.transform.smoothscale(frame, PLAYER_RENDER_SIZE)
            for frame in frames("player-sheet.png", "player-mask.png",
                                PLAYER_FRAME_RECTS["idle"])
        )
        self.player_frames_left = tuple(
            pygame.transform.smoothscale(frame, PLAYER_RENDER_SIZE)
            for frame in frames("player-sheet.png", "player-mask.png",
                                PLAYER_FRAME_RECTS["left"])
        )
        self.player_frames_right = tuple(
            pygame.transform.smoothscale(frame, PLAYER_RENDER_SIZE)
            for frame in frames("player-sheet.png", "player-mask.png",
                                PLAYER_FRAME_RECTS["right"])
        )
        self.player_icon = pygame.transform.smoothscale(
            self.player_frames[0], PLAYER_ICON_SIZE
        )

        # ---------------- 玩家弹与敌方弹幕 ----------------
        self.player_shot = pygame.transform.smoothscale(
            _compose(sheet("bullet-a-sheet.png"), sheet("bullet-a-mask.png"),
                     BULLET_RICE_RECT),
            PLAYER_SHOT_RENDER,
        )

        self.bullet_large = {
            name: pygame.transform.smoothscale(frame, BULLET_LARGE_RENDER)
            for name, frame in zip(
                BULLET_LARGE_RECTS,
                frames("bullet-a-sheet.png", "bullet-a-mask.png",
                       tuple(BULLET_LARGE_RECTS.values())),
            )
        }
        self.bullet_small = {
            name: pygame.transform.smoothscale(frame, BULLET_SMALL_RENDER)
            for name, frame in zip(
                BULLET_SMALL_RECTS,
                frames("bullet-b-sheet.png", "bullet-b-mask.png",
                       tuple(BULLET_SMALL_RECTS.values())),
            )
        }
        self.bullet_mid = {
            name: pygame.transform.smoothscale(frame, BULLET_MID_RENDER)
            for name, frame in zip(
                BULLET_MID_RECTS,
                frames("bullet-b-sheet.png", "bullet-b-mask.png",
                       tuple(BULLET_MID_RECTS.values())),
            )
        }

        # ---------------- 特效与妖精 ----------------
        effect_sheet = sheet("effect-sheet.png")

        def effect(rect: tuple[int, int, int, int],
                   size: tuple[int, int]) -> pygame.Surface:
            return pygame.transform.smoothscale(
                effect_sheet.subsurface(rect).copy(), size
            )

        self.hit_spark = effect(EFFECT_SPARK_RECT, EFFECT_SPARK_SIZE)
        self.graze_ring = effect(EFFECT_RING_RECT, EFFECT_RING_SIZE)
        self.boss_burst = effect(EFFECT_BURST_RECT, EFFECT_BURST_SIZE)
        self.fairy_frames = tuple(
            pygame.transform.smoothscale(frame, FAIRY_RENDER)
            for frame in frames("fairy-sheet.png", "fairy-mask.png", FAIRY_RECTS)
        )
        self.fairy_variant_frames = tuple(
            pygame.transform.smoothscale(frame, FAIRY_VARIANT_RENDER)
            for frame in frames(
                "fairy-variant-sheet.png", "fairy-variant-mask.png",
                FAIRY_VARIANT_RECTS,
            )
        )

        # ---------------- 掉落道具 ----------------
        # 保留原作弹型图案，以红/青/绿区分类别；标签给出道具用途缩写。
        item_sources = {
            "power": pygame.transform.smoothscale(
                self.bullet_mid["red"], ITEM_RENDER
            ),
            "point": pygame.transform.smoothscale(
                self.bullet_large["cyan"], ITEM_RENDER
            ),
            "life": pygame.transform.smoothscale(
                self.bullet_mid["green"], ITEM_RENDER
            ),
        }
        if not pygame.font.get_init():
            pygame.font.init()
        label_font = pygame.font.Font(None, 13)
        self.item_sprites = {}
        for kind, sprite in item_sources.items():
            sprite = sprite.copy()
            label = label_font.render(ITEM_LABELS[kind], True, config.WHITE)
            badge = pygame.Surface(
                (label.get_width() + 6, label.get_height() + 4), pygame.SRCALPHA
            )
            pygame.draw.rect(
                badge, (12, 5, 10, 230), badge.get_rect(), border_radius=3
            )
            pygame.draw.rect(
                badge, config.ITEM_KIND_COLORS[kind], badge.get_rect(), 1,
                border_radius=3,
            )
            badge.blit(label, label.get_rect(center=badge.get_rect().center))
            sprite.blit(badge, badge.get_rect(center=sprite.get_rect().center))
            self.item_sprites[kind] = sprite
        self.item_halo = self.graze_ring

        # ---------------- Boss 立绘 ----------------
        self.boss_faces = tuple(
            pygame.transform.smoothscale(
                _compose(sheet(image_name), sheet(mask_name), rect),
                BOSS_FACE_RENDER,
            )
            for image_name, mask_name, rect in (
                ("boss-face-a.png", "boss-face-a-mask.png", BOSS_FACE_RECTS[0]),
                ("boss-face-b.png", "boss-face-b-mask.png", BOSS_FACE_RECTS[1]),
                ("boss-face-c.png", "boss-face-c-mask.png", BOSS_FACE_RECTS[2]),
            )
        )
        self.boss_portrait = self.boss_faces[0]
