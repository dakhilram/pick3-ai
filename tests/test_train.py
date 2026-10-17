import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from train import parse, features, build, frequency, normalize, top_hit, make_model, BOX_GROUPS, box_backtest, box_log_loss, exact_any_picks
from live_tracker import ordered_picks, box_picks, reconcile, permutations
from schedule_gate import should_check, HOUSTON, CHECKS
from datetime import datetime


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

    def test_box_group_sizes(self):
        groups={''.join(map(str,d)):idx for d,idx in BOX_GROUPS}
        self.assertEqual(len(groups), 220)
        self.assertEqual(groups['123'].tolist(), [123,132,213,231,312,321])
        self.assertEqual(groups['112'].tolist(), [112,121,211])
        self.assertEqual(groups['777'].tolist(), [777])

    def test_box_backtest_counts_permutations(self):
        arr=np.tile(np.eye(10)[1],(5,1))
        result=box_backtest([arr]*3,np.tile([1,1,1],(5,1)))
        self.assertEqual(result['coverage']['top_1'],1.0)
        self.assertAlmostEqual(result['fair_expected_coverage']['top_1'],.001)
        uniform=np.full((2,10),.1)
        report=box_backtest([uniform]*3,np.asarray([[0,0,0],[1,1,1]]))
        self.assertEqual(report['groups'],220)

    def test_live_tracking_without_future_leakage(self):
        uniform = [[.1] * 10 for _ in range(3)]
        prev = {'generated_at': '2026-10-15T22:00:00+00:00',
                'games': {'morning': {'last_draw': '2026-10-15',
                                      'recent': ['123', '999'], 'probabilities': uniform}}}
        current = {'games': {'morning': {'last_draw': '2026-10-16', 'recent': ['321', '123', '999']}}}
        result = reconcile(prev, current, None)
        self.assertEqual(len(result['games']['morning']), 1)
        record = result['games']['morning'][0]
        self.assertEqual(record['actual'], '321')
        self.assertEqual(record['published_prediction_at'], prev['generated_at'])
        self.assertEqual(len(record['exact_picks']), 5)
        self.assertEqual(len(record['box_picks']), 5)
        self.assertEqual(len(reconcile(prev, current, result)['games']['morning']), 1)
        bad = {'games': {'morning': {'last_draw':'2026-10-18','recent':['222','888','123']}}}
        self.assertEqual(len(reconcile(prev,bad,{'games':{}}).get('games',{})),0)

    def test_live_group_counts(self):
        self.assertEqual(len(permutations('123')),6)
        self.assertEqual(len(permutations('112')),3)
        self.assertEqual(len(permutations('777')),1)
        uniform=[[.1]*10 for _ in range(3)]
        self.assertEqual(len(ordered_picks(uniform)),5)
        self.assertEqual(len(box_picks(uniform)),5)

    def test_straight_tie_ranking_matches_dashboard(self):
        uniform=np.full((1,10),.1)
        # 000 wins a stable tied ranking, but 999 cannot be in first five.
        self.assertEqual(top_hit([uniform]*3,np.asarray([[0,0,0]]),5),1.0)
        self.assertEqual(top_hit([uniform]*3,np.asarray([[9,9,9]]),5),0.0)

    def test_bounded_features_equivalence(self):
        from datetime import datetime, timedelta
        rows=[(datetime(2020,1,1)+timedelta(days=i),(i%10,(i+3)%10,(i+6)%10))
              for i in range(110)]
        oldX,oldY=build(rows)
        newX,newY=build(rows[-(35+60):])
        self.assertTrue(np.array_equal(oldX[-35:],newX))
        self.assertTrue(np.array_equal(oldY[-35:],newY))

    def test_houston_schedule_across_dst_and_sundays(self):
        # Every target must run in BOTH standard and daylight time.
        for month in (1, 7):
            for hour, minute in CHECKS:
                local = datetime(2026, month, 17 if month == 1 else 18,
                                 hour, minute, tzinfo=HOUSTON)
                self.assertTrue(should_check(local), (month, hour, minute))
        sunday = datetime(2026, 1, 18, 10, 35, tzinfo=HOUSTON)
        self.assertFalse(should_check(sunday))
        self.assertTrue(should_check(sunday, event="workflow_dispatch"))
        self.assertFalse(should_check(datetime(2026,1,17,9,30,tzinfo=HOUSTON)))

    def test_exact_any_ranks_groups_without_duplication(self):
        uniform=[[.1]*10 for _ in range(3)]
        picks=exact_any_picks(uniform,5)
        self.assertEqual(len(picks),5)
        self.assertEqual(len({''.join(sorted(n)) for n in picks}),5)
        same=[np.tile(np.eye(10)[1],(2,1))]*3
        self.assertLess(box_log_loss(same,np.array([[1,1,1],[1,1,1]])),.001)

    def test_models_build(self):
        self.assertIsNotNone(make_model('random_forest', 1))
        self.assertIsNotNone(make_model('gradient_boosting', 1))


if __name__ == '__main__':
    unittest.main()
