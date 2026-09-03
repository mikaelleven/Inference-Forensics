import unittest
from clamp import clamp


class HiddenClampTests(unittest.TestCase):
    def test_above_range_uses_maximum(self):
        self.assertEqual(10, clamp(12, 0, 10))

    def test_boundaries_are_inclusive(self):
        self.assertEqual(0, clamp(0, 0, 10))
        self.assertEqual(10, clamp(10, 0, 10))

    def test_invalid_range_raises(self):
        with self.assertRaises(ValueError):
            clamp(5, 10, 0)


if __name__ == "__main__":
    unittest.main()
