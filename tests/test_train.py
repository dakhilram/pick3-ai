import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from train import parse, features, build, frequency, normalize, top_hit, make_model


class Tests(unittest.TestCase):
    def test_parse_and_order(self):
        rows = parse('Pick 3 Morning,10,15,2026,1,0,4,5\nPick 3 Morning,10,14,2026,2,2,2,1\n', 'morning')
        self.assertEqual(rows[0][1], (2, 2, 2))
        self.assertEqual(rows[1][1], (1, 0, 4))

    def test_invalid_other_session_ignored(self):
        self.assertFalse(parse('Pick 3 Night,10,15,2026,1,0,4,5\n', 'morning'))

    def test_features_finite_and_shape(self):
        v = features([(1, 2, 3)] * 60)
        self.assertEqual(v.shape, (487,))
        self.assertTrue(np.isfinite(v).all())

    def test_no_future_leakage(self):
        from datetime import datetime, timedelta
        rows = [(datetime(2024, 1, 1) + timedelta(days=i), (i % 10, (i + 1) % 10, (i + 2) % 10))
                for i in range(75)]
        X, y = build(rows)
        self.assertEqual(len(X), 15)
        self.assertTrue(np.array_equal(X[0], features([r[1] for r in rows[:60]])))
        self.assertTrue(np.array_equal(y[0], rows[60][1]))

    def test_probabilities(self):
        self.assertAlmostEqual(float(frequency(np.array([0, 0])).sum()), 1)
        self.assertAlmostEqual(float(normalize([0, 0, 0]).sum()), 1)

    def test_top_k_coverage(self):
        arr = np.tile(np.eye(10)[3], (5, 1))
        truth = np.tile([3, 3, 3], (5, 1))
        self.assertEqual(top_hit([arr] * 3, truth, 1), 1.0)

    def test_models_build(self):
        self.assertIsNotNone(make_model('random_forest', 1))
        self.assertIsNotNone(make_model('gradient_boosting', 1))


if __name__ == '__main__':
    unittest.main()
