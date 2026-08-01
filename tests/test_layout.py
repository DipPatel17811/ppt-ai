"""Geometry and layout engine tests."""

import unittest

from layout import equal_columns, equal_rows, grid, weighted_rows
from utils.geometry import Rect


class RectTests(unittest.TestCase):
    def test_edges(self):
        r = Rect(10, 20, 100, 50)
        self.assertEqual((r.left, r.top, r.right, r.bottom), (10, 20, 110, 70))
        self.assertEqual(r.area, 5000)

    def test_overlaps(self):
        a = Rect(0, 0, 10, 10)
        b = Rect(9, 0, 10, 10)
        c = Rect(11, 0, 5, 5)
        self.assertTrue(a.overlaps(b))
        self.assertFalse(a.overlaps(c))

    def test_contains(self):
        outer = Rect(0, 0, 100, 100)
        inner = Rect(10, 10, 20, 20)
        self.assertTrue(outer.contains(inner))
        self.assertFalse(inner.contains(outer))

    def test_intersection(self):
        a = Rect(0, 0, 10, 10)
        b = Rect(5, 5, 10, 10)
        i = a.intersected(b)
        self.assertEqual((i.left, i.top, i.right, i.bottom), (5, 5, 10, 10))

    def test_inset_to(self):
        r = Rect(0, 0, 100, 100).inset_to(10, 20, 30, 40)
        self.assertEqual((r.x, r.y, r.width, r.height), (10, 20, 60, 40))


class PartitionTests(unittest.TestCase):
    def test_equal_columns_sum_width(self):
        area = Rect(0, 0, 100, 50)
        cols = equal_columns(area, 4, gap=2)
        self.assertEqual(len(cols), 4)
        self.assertAlmostEqual(sum(c.width for c in cols) + 3 * 2, 100)
        self.assertEqual(cols[0].y, 0)

    def test_equal_rows_sum_height(self):
        area = Rect(0, 0, 100, 50)
        rows = equal_rows(area, 5, gap=0)
        self.assertEqual(len(rows), 5)
        self.assertAlmostEqual(sum(r.height for r in rows), 50)

    def test_grid_cells(self):
        area = Rect(0, 0, 100, 100)
        cells = grid(area, rows=2, cols=3, gap_x=4, gap_y=4)
        flat = [c for row in cells for c in row]
        self.assertEqual(len(flat), 6)
        self.assertTrue(all(c.width > 0 and c.height > 0 for c in flat))

    def test_weighted_rows(self):
        area = Rect(0, 0, 100, 100)
        rows = weighted_rows(area, [1, 2, 1], gap=0)
        self.assertEqual(len(rows), 3)
        self.assertAlmostEqual(rows[1].height, 50)


if __name__ == "__main__":
    unittest.main()
