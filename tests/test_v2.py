import sys
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from schedule_gate import CENTRAL, next_draw, scheduled_at
from v2 import parse, events, rank, score, update, summarize, save_atomic, forward_metrics
from package_site import ASSETS, package


class V2Tests(unittest.TestCase):
    def archives(self):
        days = ('2026-10-19', '2026-10-20', '2026-10-21')
        return {session: list(zip(days, ('123', '321', '112')))
                for session in ('morning', 'day', 'evening', 'night')}

    def test_official_rows_and_duplicate_conflict(self):
        row = 'Pick 3 Morning,10,20,2026,1,2,3,9\n'
        self.assertEqual(parse(row + row, 'morning'), [('2026-10-20', '123')])
        with self.assertRaises(ValueError):
            parse(row + 'Pick 3 Morning,10,20,2026,3,2,1,0\n', 'morning')
        self.assertEqual(parse(row, 'night'), [])
        self.assertEqual(parse('Pick 3 Night,10,20,2026,12,2,3\n', 'night'), [])

    def test_one_engine_ranks_ordered_outcomes_into_distinct_groups(self):
        picks = rank([], 'morning')
        self.assertEqual(len(picks), 10)
        self.assertEqual(len({p['group'] for p in picks}), 10)
        self.assertAlmostEqual(picks[0]['model_probability'], .006)
        self.assertEqual(picks[0]['group'], '012')
        self.assertEqual(picks[0]['fair_probability'], .006)
        self.assertEqual(score(picks, '210')['hit_rank'], 1)
        self.assertEqual(score(picks, '210')['exact_hit'], False)

    def test_delayed_result_and_idempotent_publication(self):
        archives = self.archives()
        # At 07:00 Central, the archive's current-day rows are future results.
        before = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
        first, changed = update(archives, now=before)
        self.assertTrue(changed)
        self.assertEqual(len(first['results']), 0)
        self.assertEqual(len(first['forecasts']), 4)
        self.assertEqual(first['processed']['morning'], '2026-10-19')
        # Official Morning appears only after its draw; Day is still unpublished.
        morning_only = {key: rows if key == 'morning' else rows[:1]
                        for key, rows in archives.items()}
        later = datetime(2026, 10, 20, 17, tzinfo=timezone.utc)
        second, changed = update(morning_only, first, now=later)
        self.assertTrue(changed)
        self.assertEqual(len(second['results']), 1)
        record = second['results'][0]
        self.assertEqual(record['session'], 'morning')
        self.assertEqual(record['published_at'], first['generated_at'])
        self.assertEqual(record['predictions'], first['forecasts'][0]['predictions'])
        self.assertIsNotNone(record['estimated_coverage'])
        self.assertEqual(record['fair_coverage'], .06)
        again, changed = update(morning_only, second, now=later)
        self.assertFalse(changed)
        self.assertEqual(again, second)
        self.assertEqual(len(second['forecasts']), 8)
        self.assertEqual(first['forecasts'][0], second['forecasts'][0])

    def test_missing_pre_draw_forecast_is_not_backfilled(self):
        archives = self.archives()
        first, _ = update(archives, now=datetime(2026, 10, 20, 12, tzinfo=timezone.utc))
        first['forecasts'] = []
        second, _ = update(archives, first, now=datetime(2026, 10, 21, 6, tzinfo=timezone.utc))
        self.assertEqual(len(second['results']), 4)
        self.assertTrue(all(row['predictions'] is None and row['hit_rank'] is None for row in second['results']))
        self.assertEqual(second['forward']['morning']['draws'], 0)

    def test_saturday_sunday_and_dst(self):
        self.assertEqual(next_draw('morning', datetime(2026, 10, 24, 23, tzinfo=CENTRAL)).date(), date(2026, 10, 26))
        self.assertEqual(scheduled_at('morning', '2026-07-18').astimezone(timezone.utc).hour, 15)
        self.assertEqual(scheduled_at('morning', '2026-01-17').astimezone(timezone.utc).hour, 16)
        self.assertEqual(next_draw('night', datetime(2026, 11, 1, 8, tzinfo=timezone.utc)).date(), date(2026, 11, 2))

    def test_history_metrics_keep_estimates_separate(self):
        records = [dict(score(rank([], 'morning'), '210')),
                   dict(score(rank([], 'morning'), '999'))]
        result = summarize(records)
        self.assertEqual(result['draws'], 2)
        self.assertEqual(result['top_1'], .5)
        self.assertEqual(result['top_10'], .5)
        self.assertGreater(result['estimated_top_10'], result['fair_top_10'] - .00001)
        legacy = dict(records[0], estimated_coverage=None)
        self.assertEqual(forward_metrics([dict(legacy, session='morning')])['morning']['draws'], 0)

    def test_official_correction_stops_publication(self):
        first, _ = update(self.archives(), now=datetime(2026, 10, 20, 12, tzinfo=timezone.utc))
        changed = self.archives()
        changed['morning'][0] = ('2026-10-19', '999')
        with self.assertRaisesRegex(ValueError, 'correction'):
            update(changed, first, now=datetime(2026, 10, 20, 17, tzinfo=timezone.utc))

    def test_atomic_json_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'predictions.json'
            save_atomic(path, {'schema_version': 9, 'sessions': {}})
            self.assertEqual(json.loads(path.read_text())['schema_version'], 9)
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])

    def test_pages_package_contains_only_active_v2_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            output = package(Path(directory) / 'site')
            files = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
            self.assertEqual(files, set(ASSETS))
            self.assertEqual(json.loads((output / 'data/predictions.json').read_text())['schema_version'], 9)


if __name__ == '__main__':
    unittest.main()
