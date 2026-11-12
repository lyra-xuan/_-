"""碰撞检测核心模块。

本项目为《问题求解》课程大作业，碰撞检测是核心评分点，因此独立成模块，
集中实现多种算法，便于复用、单独验证与在报告中讲解：

- ``aabb``          轴对齐包围盒，矩形物体的快速粗筛；
- ``circle_circle`` 圆-圆判定，弹幕游戏的主力（子弹与机体均以圆近似）；
- ``segment_circle`` 线段-圆判定，用于高速子弹的“扫掠检测”，防止穿模；
- ``SpatialGrid``   均匀空间网格，碰撞检测的宽相位（broad-phase）优化。

双层判定（命中区 hit_radius / 擦弹区 graze_radius）由上层逻辑基于
本模块的几何函数组合完成，见 ``Game._check_collisions``。
"""
from __future__ import annotations

import math

import pygame


# --------------------------------------------------------------------------- #
# 基础几何判定
# --------------------------------------------------------------------------- #
def aabb(a: pygame.Rect, b: pygame.Rect) -> bool:
    """轴对齐包围盒相交测试。边界恰好接触不算相交。"""
    return a.left < b.right and a.right > b.left and a.top < b.bottom and a.bottom > b.top


def circle_circle(x1: float, y1: float, r1: float,
                  x2: float, y2: float, r2: float) -> bool:
    """圆-圆相交测试：圆心距 <= 半径之和即视为相交（含相切）。"""
    dx = x1 - x2
    dy = y1 - y2
    rr = r1 + r2
    return dx * dx + dy * dy <= rr * rr


def point_in_circle(px: float, py: float, cx: float, cy: float, r: float) -> bool:
    """点是否落在圆内（含圆周）。"""
    dx = px - cx
    dy = py - cy
    return dx * dx + dy * dy <= r * r


def segment_circle(x1: float, y1: float, x2: float, y2: float,
                   cx: float, cy: float, r: float) -> bool:
    """线段-圆相交测试。

    把高速子弹一帧内的位移视为线段 [P1, P2]，判断该线段是否与目标圆相交。
    相比只在帧末做点-圆判定，可避免“子弹太快直接跨过目标”的穿模问题。

    做法：求圆心在线段上的投影点，夹紧到线段范围内，再判断该点是否落入圆内。
    """
    dx = x2 - x1
    dy = y2 - y1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-9:                      # 线段退化为点（浮点容差）
        return point_in_circle(x1, y1, cx, cy, r)

    # 圆心在线段方向上的投影参数 t，并夹紧到 [0, 1]
    t = ((cx - x1) * dx + (cy - y1) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))

    # 线段上离圆心最近的点
    nx = x1 + t * dx
    ny = y1 + t * dy
    return point_in_circle(nx, ny, cx, cy, r)


# --------------------------------------------------------------------------- #
# 宽相位优化：均匀空间网格
# --------------------------------------------------------------------------- #
class SpatialGrid:
    """均匀空间网格，将朴素 O(n^2) 两两检测降为近似 O(n)。

    物体按中心点插入所属格子；查询时只遍历查询圆外接矩形覆盖的格子。

    前提：单个物体的半径远小于格子边长（本项目子弹/机体均满足）。
    """

    def __init__(self, width: int, height: int, cell_size: int) -> None:
        self.cell_size = cell_size
        self.cols = int(math.ceil(width / cell_size))
        self.rows = int(math.ceil(height / cell_size))
        self._cells: dict[tuple[int, int], list] = {}

    def clear(self) -> None:
        self._cells.clear()

    def _key(self, x: float, y: float) -> tuple[int, int]:
        """把世界坐标映射到格子下标（超出范围时夹紧到边界格）。"""
        col = max(0, min(self.cols - 1, int(x // self.cell_size)))
        row = max(0, min(self.rows - 1, int(y // self.cell_size)))
        return col, row

    def insert(self, obj, x: float, y: float) -> None:
        """按中心点 (x, y) 把物体放入对应格子。"""
        self._cells.setdefault(self._key(x, y), []).append(obj)

    def query(self, x: float, y: float, radius: float) -> list:
        """返回可能与以 (x, y) 为圆心、radius 为半径的圆相交的候选物体。"""
        col0, row0 = self._key(x - radius, y - radius)
        col1, row1 = self._key(x + radius, y + radius)
        found: list = []
        for col in range(col0, col1 + 1):
            for row in range(row0, row1 + 1):
                cell = self._cells.get((col, row))
                if cell:
                    found.extend(cell)
        return found
