"""Forward-only, shared lightweight Texas Pick 3 prediction and publication."""
import csv
import copy
import io
import itertools
import json
import os
import tempfile
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from schedule_gate import DRAW_TIMES, next_draw, scheduled_at

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'web' / 'data' / 'predictions.json'
LEGACY = ROOT / 'web' / 'data' / 'live_history.json'
BASE = 'https://www.texaslottery.com/export/sites/lottery/Games/Pick_3/Winning_Numbers/'
SESSIONS = tuple(DRAW_TIMES)
ORDERS = tuple(''.join(map(str, digits)) for digits in itertools.product(range(10), repeat=3))


def parse(text, session):
    found = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 7 or row[0].strip().lower() != f'pick 3 {session}':
            continue
        try:
            day = date(int(row[3]), int(row[1]), int(row[2])).isoformat()
            values = [int(value) for value in row[4:7]]
        except ValueError:
            continue
        if any(value < 0 or value > 9 for value in values):
            continue
        number = ''.join(map(str, values))
        if day in found and found[day] != number:
            raise ValueError(f'Conflicting official rows: {session} {day}')
        found[day] = number
    return sorted(found.items())


def fetch_official():
    archives = {}
    for session in SESSIONS:
        request = urllib.request.Request(BASE + f'pick3{session}.csv',
                                         headers={'User-Agent': 'Pick3AI-lightweight/2'})
        with urllib.request.urlopen(request, timeout=45) as response:
            rows = parse(response.read().decode('utf-8-sig'), session)
        if len(rows) < 160:
            raise ValueError(f'Incomplete official archive: {session}')
        archives[session] = rows
    return archives


def events(archives, now):
    result = []
    for session, rows in archives.items():
        for draw_date, number in rows:
            instant = scheduled_at(session, date.fromisoformat(draw_date)).astimezone(timezone.utc)
            if instant <= now:
                result.append((instant, session, draw_date, number))
    return sorted(result)


def position_probabilities(prior, session):
    """One global prior with session-specific adjustments; no play-type models."""
    global_rows = [row[3] for row in prior[-240:]]
    local_rows = [row[3] for row in prior if row[1] == session][-80:]
    result = []
    for position in range(3):
        def smoothed(rows):
            counts = [2.0] * 10
            for number in rows:
                counts[int(number[position])] += 1
            return [value / sum(counts) for value in counts]
        shared, local = smoothed(global_rows), smoothed(local_rows)
        result.append([0.75 * shared[i] + 0.25 * local[i] for i in range(10)])
    return result


def rank(prior, session):
    probabilities = position_probabilities(prior, session)
    groups = {}
    for number in ORDERS:
        a, b, c = map(int, number)
        mass = probabilities[0][a] * probabilities[1][b] * probabilities[2][c]
        key = ''.join(sorted(number))
        item = groups.setdefault(key, {'group': key, 'representative': number,
                                       'model_probability': 0.0, 'exact_probability': -1.0})
        item['model_probability'] += mass
        if mass > item['exact_probability']:
            item['exact_probability'] = mass
            item['representative'] = number
    chosen = sorted(groups.values(), key=lambda item: (-item['model_probability'], item['group']))[:10]
    for item in chosen:
        item['fair_probability'] = len(set(itertools.permutations(item['group']))) / 1000
        item['model_probability'] = round(item['model_probability'], 9)
        item['exact_probability'] = round(item['exact_probability'], 9)
    return chosen


def score(predictions, actual):
    group = ''.join(sorted(actual))
    hit = next((i + 1 for i, pick in enumerate(predictions) if pick['group'] == group), None)
    masses = [pick.get('model_probability') for pick in predictions]
    return {'hit_rank': hit,
            'exact_hit': any(pick.get('representative') == actual for pick in predictions),
            'fair_top_1': round(predictions[0]['fair_probability'], 6),
            'fair_top_5': round(sum(pick['fair_probability'] for pick in predictions[:5]), 6),
            'fair_coverage': round(sum(pick['fair_probability'] for pick in predictions), 6),
            'estimated_coverage': round(sum(masses), 6) if all(m is not None for m in masses) else None}


def summarize(rows):
    rows = [row for row in rows if row.get('fair_coverage') is not None]
    n = len(rows)
    if not n:
        return {'draws': 0}
    return {'draws': n,
            'top_1': sum(row['hit_rank'] == 1 for row in rows) / n,
            'top_5': sum(row['hit_rank'] is not None and row['hit_rank'] <= 5 for row in rows) / n,
            'top_10': sum(row['hit_rank'] is not None for row in rows) / n,
            'fair_top_1': sum(row.get('fair_top_1') or 0 for row in rows) / n,
            'fair_top_5': sum(row.get('fair_top_5') or 0 for row in rows) / n,
            'fair_top_10': sum(row['fair_coverage'] for row in rows) / n,
            'estimated_top_10': (sum(row['estimated_coverage'] for row in rows) / n
                                 if all(row.get('estimated_coverage') is not None for row in rows) else None)}


def backtest(ordered, limit=200):
    """Walk forward through earlier official draws; no target outcome enters its forecast."""
    targets = {session: {row[2] for row in ordered if row[1] == session} for session in SESSIONS}
    targets = {session: set(sorted(days)[-limit:]) for session, days in targets.items()}
    prior, results = [], defaultdict(list)
    for row in ordered:
        if row[2] in targets[row[1]] and len(prior) >= 240:
            results[row[1]].append(score(rank(prior, row[1]), row[3]))
        prior.append(row)
    return {session: summarize(results[session]) for session in SESSIONS}


def forward_metrics(records):
    """Only count published forecasts from this engine, not migrated V2 variants."""
    return {session: summarize([row for row in records if row['session'] == session
                                and row.get('estimated_coverage') is not None])
            for session in SESSIONS}


def migrate(previous, legacy):
    data = {'schema_version': 9, 'generated_at': None, 'source': BASE,
            'model': 'shared_frequency_v2', 'processed': {}, 'sessions': {},
            'forecasts': [], 'results': [], 'backtest': {}, 'forward': {}}
    if not previous:
        return data
    if previous.get('schema_version') == 9:
        return copy.deepcopy(previous)
    if previous.get('schema_version') != 8:
        raise ValueError('Unsupported existing publication schema')
    for session in SESSIONS:
        old = previous['games'][session]
        data['processed'][session] = old['last_draw']
        for row in (legacy or {}).get('games', {}).get(session, []):
            picks = row.get('v2_top10')
            timestamp = row.get('published_prediction_at')
            if not picks or len(picks) != 10 or not timestamp:
                continue
            if datetime.fromisoformat(timestamp) >= scheduled_at(session, date.fromisoformat(row['draw_date'])):
                continue
            data['results'].append({'session': session, 'draw_date': row['draw_date'],
                                    'actual': row['actual'], 'verified_at': None,
                                    'published_at': timestamp,
                                    'predictions': [{'group': value} for value in picks],
                                    'hit_rank': row.get('v2_hit_rank'), 'exact_hit': None,
                                    'fair_top_1': len(set(itertools.permutations(picks[0]))) / 1000,
                                    'fair_top_5': sum(len(set(itertools.permutations(v))) for v in picks[:5]) / 1000,
                                    'fair_coverage': row.get('v2_fair_probability'),
                                    'estimated_coverage': None, 'source': 'legacy_v2'})
        if len(old.get('v2_top10', [])) == 10 and previous.get('generated_at'):
            published = datetime.fromisoformat(previous['generated_at'])
            target = next_draw(session, published)
            predictions = [{'group': value, 'representative': None,
                            'model_probability': None, 'exact_probability': None,
                            'fair_probability': len(set(itertools.permutations(value))) / 1000}
                           for value in old['v2_top10']]
            data['forecasts'].append({'session': session, 'target_draw': target.date().isoformat(),
                                      'published_at': previous['generated_at'],
                                      'source_through': {name: previous['games'][name]['last_draw'] for name in SESSIONS},
                                      'predictions': predictions, 'source': 'legacy_v2'})
    return data


def update(archives, previous=None, legacy=None, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('now must include a timezone')
    data = migrate(previous, legacy)
    ordered = events(archives, now)
    if not ordered:
        raise ValueError('No verified official draws')
    known = data['processed']
    archive_lookup = {session: dict(rows) for session, rows in archives.items()}
    for session, through in known.items():
        if through not in archive_lookup[session]:
            raise ValueError(f'Official archive lost processed draw: {session} {through}')
        published_result = data.get('sessions', {}).get(session, {}).get('latest_result')
        if published_result and archive_lookup[session][through] != published_result:
            raise ValueError(f'Official correction requires review: {session} {through}')
    for record in data['results']:
        official = archive_lookup[record['session']].get(record['draw_date'])
        if official and official != record['actual']:
            raise ValueError(f'Official correction requires review: {record["session"]} {record["draw_date"]}')
    for session in SESSIONS:
        if session not in known:
            known[session] = max(row[2] for row in ordered if row[1] == session)
    unseen = [row for row in ordered if row[2] > known[row[1]]]
    if not unseen and data['sessions']:
        return data, False
    published = now.astimezone(timezone.utc).isoformat()
    for _, session, target, actual in unseen:
        draw_at = scheduled_at(session, date.fromisoformat(target))
        candidates = [item for item in data['forecasts']
                      if item['session'] == session and item['target_draw'] == target
                      and datetime.fromisoformat(item['published_at']) < draw_at]
        record = {'session': session, 'draw_date': target, 'actual': actual,
                  'verified_at': published, 'published_at': None, 'predictions': None,
                  'hit_rank': None, 'exact_hit': None, 'fair_coverage': None,
                  'fair_top_1': None, 'fair_top_5': None, 'estimated_coverage': None}
        if candidates:
            chosen = max(candidates, key=lambda item: item['published_at'])
            record.update(score(chosen['predictions'], actual))
            record['published_at'] = chosen['published_at']
            record['predictions'] = chosen['predictions']
        data['results'].append(record)
        known[session] = target
    data['backtest'] = backtest(ordered)
    data['generated_at'] = published
    data['official_checked_at'] = published
    data['sessions'] = {}
    for session in SESSIONS:
        target = next_draw(session, now)
        predictions = rank(ordered, session)
        rows = archives[session]
        latest = next(number for day, number in reversed(rows) if day == known[session])
        data['sessions'][session] = {'last_draw': known[session], 'latest_result': latest,
                                     'draws': len(rows), 'target_draw': target.isoformat(),
                                     'predictions': predictions, 'published_at': published}
        data['forecasts'].append({'session': session, 'target_draw': target.date().isoformat(),
                                  'published_at': published, 'source_through': dict(known),
                                  'predictions': predictions})
    data['forward'] = forward_metrics(data['results'])
    return data, True


def save_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write('\n')
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    previous = json.loads(OUTPUT.read_text(encoding='utf-8')) if OUTPUT.exists() else None
    legacy = json.loads(LEGACY.read_text(encoding='utf-8')) if previous and previous.get('schema_version') == 8 and LEGACY.exists() else None
    data, changed = update(fetch_official(), previous, legacy)
    if changed:
        save_atomic(OUTPUT, data)
        print('Published', len(data['results']), 'official records and four forecasts')
    else:
        print('No new official draw; publication unchanged')


if __name__ == '__main__':
    main()
