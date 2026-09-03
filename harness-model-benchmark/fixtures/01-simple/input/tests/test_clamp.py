import unittest
from clamp import clamp


class ClampTests(unittest.TestCase):
    def test_value_inside_range_is_unchanged(self):
        self.assertEqual(5, clamp(5, 0, 10))

    def test_value_below_range_uses_minimum(self):
        self.assertEqual(0, clamp(-2, 0, 10))


if __name__ == "__main__":
    unittest.main()
