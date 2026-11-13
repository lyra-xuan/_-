"""基础几何判定与空间网格的单元测试。

覆盖验收标准要求的四类情形：几何边界、相切、静止线段与网格边缘。
这些用例直接针对 ``collision`` 中的几何函数，不依赖游戏循环。
"""
import unittest

import pygame

from src import collision


class AabbTests(unittest.TestCase):
    def test_separated_rects_do_not_intersect(self) -> None:
        self.assertFalse(
            collision.aabb(pygame.Rect(0, 0, 10, 10), pygame.Rect(20, 0, 10, 10))
        )

    def test_partially_overlapping_rects_intersect(self) -> None:
        self.assertTrue(
            collision.aabb(pygame.Rect(0, 0, 10, 10), pygame.Rect(5, 5, 10, 10))
        )

    def test_edge_touching_rects_do_not_intersect(self) -> None:
        """边界恰好接触不算相交（严格小于比较）。"""
        self.assertFalse(
            collision.aabb(pygame.Rect(0, 0, 10, 10), pygame.Rect(10, 0, 10, 10))
        )
        self.assertFalse(
            collision.aabb(pygame.Rect(0, 0, 10, 10), pygame.Rect(0, 10, 10, 10))
        )

    def test_contained_rect_intersects(self) -> None:
        self.assertTrue(
            collision.aabb(pygame.Rect(0, 0, 50, 50), pygame.Rect(10, 10, 5, 5))
        )


class CircleCircleTests(unittest.TestCase):
    def test_separated_circles_do_not_intersect(self) -> None:
        self.assertFalse(collision.circle_circle(0, 0, 5, 11, 0, 5))

    def test_overlapping_circles_intersect(self) -> None:
        self.assertTrue(collision.circle_circle(0, 0, 5, 8, 0, 5))

    def test_externally_tangent_circles_intersect(self) -> None:
        """相切视为相交（距离 <= 半径和）。"""
        self.assertTrue(collision.circle_circle(0, 0, 5, 10, 0, 5))

    def test_concentric_circles_intersect(self) -> None:
        self.assertTrue(collision.circle_circle(0, 0, 5, 0, 0, 2))


class PointInCircleTests(unittest.TestCase):
    def test_point_inside_circle(self) -> None:
        self.assertTrue(collision.point_in_circle(1, 1, 0, 0, 5))

    def test_point_on_circle_boundary_counts_as_inside(self) -> None:
        self.assertTrue(collision.point_in_circle(5, 0, 0, 0, 5))

    def test_point_outside_circle(self) -> None:
        self.assertFalse(collision.point_in_circle(6, 0, 0, 0, 5))


class SegmentCircleTests(unittest.TestCase):
    def test_segment_crossing_circle_with_both_ends_outside(self) -> None:
        """两端都在圆外但线段穿过圆，扫掠检测必须命中。"""
        self.assertTrue(collision.segment_circle(-10, 0, 10, 0, 0, 0, 3))

    def test_segment_endpoint_grazing_circle_counts_as_hit(self) -> None:
        self.assertTrue(collision.segment_circle(0, 0, 10, 0, 10, 0, 1))

    def test_segment_avoiding_circle_is_not_a_hit(self) -> None:
        self.assertFalse(collision.segment_circle(-10, -10, -5, -10, 0, 0, 2))

    def test_stationary_segment_falls_back_to_point_test(self) -> None:
        """静止线段（退化为点）应退化为点-圆判定。"""
        self.assertTrue(collision.segment_circle(3, 4, 3, 4, 0, 0, 5))
        self.assertFalse(collision.segment_circle(3, 4, 3, 4, 0, 0, 4.9))


class SpatialGridTests(unittest.TestCase):
    def setUp(self) -> None:
        self.grid = collision.SpatialGrid(200, 200, 96)

    def test_query_returns_object_in_same_cell(self) -> None:
        marker = object()
        self.grid.insert(marker, 10, 10)

        self.assertEqual(self.grid.query(10, 10, 1.0), [marker])

    def test_query_collects_objects_across_cells(self) -> None:
        left = object()
        right = object()
        self.grid.insert(left, 10, 10)
        self.grid.insert(right, 190, 190)

        found = self.grid.query(100, 100, 100.0)

        self.assertIn(left, found)
        self.assertIn(right, found)

    def test_out_of_range_position_is_clamped_to_border_cell(self) -> None:
        """越界坐标夹紧到边界格，且不会出现在远端的查询结果里。"""
        far = object()
        self.grid.insert(far, 5000, 5000)

        self.assertNotIn(far, self.grid.query(10, 10, 1.0))
        self.assertIn(far, self.grid.query(199, 199, 1.0))

    def test_clear_removes_all_objects(self) -> None:
        self.grid.insert(object(), 10, 10)

        self.grid.clear()

        self.assertEqual(self.grid.query(10, 10, 1.0), [])

    def test_cell_count_is_ceiling_of_size_over_cell_size(self) -> None:
        self.assertEqual(self.grid.cols, 3)
        self.assertEqual(self.grid.rows, 3)


if __name__ == "__main__":
    unittest.main()
