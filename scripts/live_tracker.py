"""Forward-only live Pick 3 tracking. No historical backfill or future leakage."""
import itertools
import json
import os
from pathlib import Path


def ordered_picks(probabilities, count=5):
    picks = []
    for i, j, k in itertools.product(range(10), repeat=3):
        picks.append((f'{i}{j}{k}', float(probabilities[0][i] * probabilities[1][j] * probabilities[2][k])))
    return [n for n, _ in sorted(picks, key=lambda v: (-v[1], v[0]))[:count]]


def box_picks(probabilities, count=5):
    groups = {}
    for i, j, k in itertools.product(range(10), repeat=3):
        key = ''.join(sorted(f'{i}{j}{k}'))
        groups[key] = groups.get(key, 0.) + float(probabilities[0][i] * probabilities[1][j] * probabilities[2][k])
    return [n for n, _ in sorted(groups.items(), key=lambda v: (-v[1], v[0]))[:count]]


def permutations(number):
    return {''.join(p) for p in itertools.permutations(number)}


def reconcile(previous, current, history):
    """Evaluate a saved forecast only for exactly one newly added official draw."""
    records = history if isinstance(history, dict) else {'schema_version': 1, 'games': {}}
    records.setdefault('games', {})
    if not previous or not isinstance(previous.get('games'), dict):
        return records
    for session, actual_game in current['games'].items():
        old = previous['games'].get(session)
        if not old:
            continue
        dates_differ = actual_game['last_draw'] != old['last_draw']
        if not dates_differ:
            continue
        # Require the old last result immediately before the newly observed result.
        if len(actual_game.get('recent', [])) < 2 or actual_game['recent'][1] != old['recent'][0]:
            print('Skipping nonconsecutive live outcome:', session)
            continue
        draw_date = actual_game['last_draw']
        prior_timestamp = previous.get('generated_at')
        if not prior_timestamp:
            continue
        existing = records['games'].setdefault(session, [])
        if any(r['draw_date'] == draw_date for r in existing):
            continue
        exact = ordered_picks(old['probabilities'])
        boxes = box_picks(old['probabilities'])
        winning = actual_game['recent'][0]
        any_exact_picks = set().union(*(permutations(n) for n in exact))
        box_covered = set().union(*(permutations(n) for n in boxes))
        record = {
            'draw_date': draw_date,
            'published_prediction_at': prior_timestamp,
            'last_known_draw': old['last_draw'],
            'actual': winning,
            'exact_picks': exact,
            'box_picks': boxes,
            'exact_hit': winning in exact,
            'exact_any_hit': winning in any_exact_picks,
            'box_hit': winning in box_covered,
            'exact_fair_probability': len(exact)/1000,
            'exact_any_fair_probability': len(any_exact_picks)/1000,
            'box_fair_probability': len(box_covered)/1000,
        }
        existing.append(record)
        records['games'][session] = existing[-400:]
    return records


def save_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    os.replace(tmp, path)
