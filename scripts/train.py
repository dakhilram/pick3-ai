"""PICK3 AI: leakage-aware comparison of statistical and tree models.

Research-only model scores are not calibrated lottery winning probabilities.
"""
import csv
import io
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from live_tracker import reconcile, save_atomic
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier

BASE = 'https://www.texaslottery.com/export/sites/lottery/Games/Pick_3/Winning_Numbers/'
GAMES = ('morning', 'day', 'evening', 'night')
ROOT = Path(__file__).resolve().parents[1]
WINDOW = 60
MAX_TRAIN = 1800
LABELS = np.arange(10)
EPS = 1e-8


def parse(data, game):
    records = {}
    for row in csv.reader(io.StringIO(data)):
        if len(row) < 7 or game not in row[0].lower():
            continue
        try:
            month, day, year = map(int, row[1:4])
            digits = tuple(map(int, row[4:7]))
            date = datetime(year, month, day)
        except (ValueError, TypeError):
            continue
        if all(0 <= d <= 9 for d in digits):
            if date in records and records[date] != digits:
                raise ValueError(f'Conflicting draws for {game} {date.date()}')
            records[date] = digits
    return sorted(records.items())


def features(history):
    """Features calculated entirely from preceding results."""
    a = np.asarray(history[-WINDOW:], dtype=int)
    if len(a) < WINDOW or a.shape[1:] != (3,):
        raise ValueError('60 prior draws are required')
    values = []
    for p in range(3):
        seq = a[:, p]
        for length in (10, 20, 40, 60):
            values.extend((np.bincount(seq[-length:], minlength=10) / length).tolist())
        values.extend((seq[-6:] / 9).tolist())
        values.append(float(np.mean(seq)) / 9)
        values.append(float(np.std(seq)) / 5)
    sums = a.sum(axis=1)
    for length in (10, 30, 60):
        values.extend([float(np.mean(sums[-length:])) / 27,
                       float(np.std(sums[-length:])) / 14])
    values.extend((np.bincount(sums, minlength=28) / len(sums)).tolist())
    repeats = np.asarray([len(set(row)) for row in a])
    values.extend([(repeats == k).mean() for k in (1, 2, 3)])
    values.extend([(a % 2).mean(axis=0).tolist()][0])
    for p in range(3):
        for q in range(p + 1, 3):
            pair = a[:, p] * 10 + a[:, q]
            values.extend((np.bincount(pair[-30:], minlength=100) / 30).tolist())
    values.extend((a[-1] / 9).tolist())
    return np.asarray(values, dtype=float)


def build(rows):
    nums = [digits for _, digits in rows]
    X = np.asarray([features(nums[:i]) for i in range(WINDOW, len(nums))])
    y = np.asarray(nums[WINDOW:], dtype=int)
    return X, y


def frequency(y):
    if len(y) == 0:
        return np.full(10, .1)
    counts = np.bincount(y, minlength=10).astype(float) + 1
    return counts / counts.sum()


def normalize(p):
    p = np.maximum(np.asarray(p, dtype=float), EPS)
    return p / p.sum(axis=-1, keepdims=True)


def full_prob(model, X):
    raw = model.predict_proba(X)
    result = np.full((len(X), 10), EPS)
    for i, digit in enumerate(model.classes_):
        result[:, int(digit)] = raw[:, i]
    return normalize(result)


def make_model(kind, seed):
    if kind == 'random_forest':
        return RandomForestClassifier(n_estimators=60, max_depth=7,
                                      min_samples_leaf=12, random_state=seed, n_jobs=2)
    if kind == 'gradient_boosting':
        return HistGradientBoostingClassifier(max_iter=45, max_leaf_nodes=12,
                                              l2_regularization=8, min_samples_leaf=30,
                                              learning_rate=.04, random_state=seed)
    raise ValueError(kind)


def score(probs, actual):
    return float(-np.log(np.maximum(probs[np.arange(len(actual)), actual], EPS)).mean())


def top_hit(prob_by_position, truth, k):
    """Top-k exact-order coverage, using all three independent positional scores."""
    # Each test row has a score for all 1000 combinations.
    universe = np.asarray([(i, j, k0) for i in range(10)
                           for j in range(10) for k0 in range(10)], dtype=int)
    combined = (prob_by_position[0][:, universe[:, 0]] *
                prob_by_position[1][:, universe[:, 1]] *
                prob_by_position[2][:, universe[:, 2]])
    # Stable full ranking, matching the dashboard's digit-order tie break.
    idx = np.argsort(-combined, axis=1, kind='stable')[:, :k]
    actual = truth[:, 0] * 100 + truth[:, 1] * 10 + truth[:, 2]
    return float(np.mean(np.any(idx == actual[:, None], axis=1)))



def box_groups():
    """220 unique unordered triples; each stores all 1/3/6 straight indices."""
    from itertools import combinations_with_replacement, permutations
    return [(tuple(digits), np.asarray(sorted({100*a+10*b+c for a,b,c in permutations(digits)}), dtype=int))
            for digits in combinations_with_replacement(range(10), 3)]


BOX_GROUPS = box_groups()


def box_backtest(prob_by_position, truth, ks=(1, 5, 10, 20)):
    """Rank unique box groups by summed permutation masses, score actual unordered result."""
    universe = np.asarray([(i,j,k) for i in range(10) for j in range(10)
                           for k in range(10)], dtype=int)
    probs = (prob_by_position[0][:, universe[:,0]] *
             prob_by_position[1][:, universe[:,1]] *
             prob_by_position[2][:, universe[:,2]])
    masses = np.column_stack([probs[:, indexes].sum(axis=1) for _,indexes in BOX_GROUPS])
    # Stable deterministic tie handling: canonical ascending triple.
    ranked = np.argsort(-masses, axis=1, kind='stable')
    truth_labels = [tuple(sorted(map(int, row))) for row in truth]
    lookup = {digits:i for i,(digits,_) in enumerate(BOX_GROUPS)}
    targets = np.asarray([lookup[d] for d in truth_labels])
    coverage, fair = {}, {}
    sizes = np.asarray([len(indices) for _,indices in BOX_GROUPS])
    for k in ks:
        chosen = ranked[:, :k]
        coverage[f'top_{k}'] = round(float(np.mean(np.any(chosen == targets[:,None], axis=1))), 5)
        fair[f'top_{k}'] = round(float(np.mean(sizes[chosen].sum(axis=1)/1000)), 5)
    return {'coverage':coverage, 'fair_expected_coverage':fair,
            'groups':len(BOX_GROUPS)}


def box_log_loss(position_probs, truth):
    """Proper log score of unordered results: sum every distinct permutation's mass."""
    by_pos = [np.asarray(p) for p in position_probs]
    totals = []
    for t, digits in enumerate(truth):
        group = sorted(set(__import__('itertools').permutations(map(int, digits))))
        mass = sum(by_pos[0][t,a] * by_pos[1][t,b] * by_pos[2][t,c]
                   for a,b,c in group)
        totals.append(-np.log(max(mass, EPS)))
    return float(np.mean(totals))


def exact_any_picks(probabilities, count=5):
    """Rank unordered groups by Any coverage; choose best exact order within each group."""
    import itertools
    groups = {}
    for a,b,c in itertools.product(range(10), repeat=3):
        number = f'{a}{b}{c}'
        key = ''.join(sorted(number))
        score = float(probabilities[0][a] * probabilities[1][b] * probabilities[2][c])
        group = groups.setdefault(key, {'score':0.,'best':number,'best_score':-1.})
        group['score'] += score
        if score > group['best_score'] or (score == group['best_score'] and number < group['best']):
            group.update(best=number,best_score=score)
    chosen = sorted(groups.values(), key=lambda g:(-g['score'],g['best']))[:count]
    return [g['best'] for g in chosen]


def predict_one(rows):
    if len(rows) < 700:
        raise ValueError('Insufficient historical draws')
    # Build only the latest bounded training window plus its preceding feature history.
    # This preserves exactly the same X/y while avoiding thousands of discarded rows.
    X, y = build(rows[-(MAX_TRAIN + WINDOW):])
    n = len(X)
    test_n = min(300, max(100, n // 6))
    val_n = min(300, max(100, n // 6))
    train_end = n - test_n - val_n
    if train_end < 250:
        raise ValueError('Insufficient chronological training data')
    # Two expanding-window validation folds before an untouched final test.
    folds = [(train_end - 2 * val_n, train_end - val_n),
             (train_end - val_n, train_end)]
    if folds[0][0] < 250:
        raise ValueError('Not enough history for walk-forward folds')
    kinds = ('smoothed_frequency', 'random_forest', 'gradient_boosting', 'ensemble')
    metrics = []
    output = []
    test_predictions = []
    selection = []
    alternatives = {name: [] for name in ('smoothed_frequency', 'random_forest', 'gradient_boosting', 'ensemble')}
    validation_candidates = [{kind: [] for kind in kinds} for _ in folds]
    test_candidates = {kind: [] for kind in kinds}
    for p in range(3):
        losses = {kind: [] for kind in kinds}
        for fold_idx, (valid_start, valid_end) in enumerate(folds):
            truth = y[valid_start:valid_end, p]
            base = np.tile(frequency(y[:valid_start, p]), (len(truth), 1))
            fold_probs = {'smoothed_frequency': base}
            for kind in ('random_forest', 'gradient_boosting'):
                m = make_model(kind, 700 + p + 20 * fold_idx)
                m.fit(X[:valid_start], y[:valid_start, p])
                fold_probs[kind] = full_prob(m, X[valid_start:valid_end])
            fold_probs['ensemble'] = normalize((base + fold_probs['random_forest'] +
                                                fold_probs['gradient_boosting']) / 3)
            for kind, values in fold_probs.items():
                losses[kind].append(score(values, truth))
                validation_candidates[fold_idx][kind].append(values)
        validation_losses = {kind: float(np.mean(values)) for kind, values in losses.items()}
        best = min(kinds, key=lambda name: validation_losses[name])
        # Conservative margin: modest retrospective differences are treated as noise.
        if validation_losses['smoothed_frequency'] - validation_losses[best] < .005:
            best = 'smoothed_frequency'
        selection.append(best)
        test_train = n - test_n
        baseline = frequency(y[:test_train, p])
        preds = {'smoothed_frequency': np.tile(baseline, (test_n, 1))}
        next_preds = {'smoothed_frequency': frequency(y[:, p])}
        for kind in ('random_forest', 'gradient_boosting'):
            m = make_model(kind, 900 + p)
            m.fit(X[:test_train], y[:test_train, p])
            preds[kind] = full_prob(m, X[test_train:])
            m.fit(X, y[:, p])
            next_preds[kind] = full_prob(m, features([r[1] for r in rows])[None, :])[0]
        preds['ensemble'] = normalize((preds['smoothed_frequency'] +
                                       preds['random_forest'] + preds['gradient_boosting']) / 3)
        next_preds['ensemble'] = normalize((next_preds['smoothed_frequency'] +
                                            next_preds['random_forest'] + next_preds['gradient_boosting']) / 3)
        for kind in kinds:
            test_candidates[kind].append(preds[kind])
        selected_test = preds[best]
        test_predictions.append(selected_test)
        output.append(normalize(next_preds[best]).round(9).tolist())
        for name in alternatives:
            alternatives[name].append(normalize(next_preds[name]).round(9).tolist())
        metrics.append({
            'position': p + 1, 'selected': best,
            'validation_log_loss': round(validation_losses[best], 5),
            'model_log_loss': round(validation_losses['random_forest'], 5),
            'baseline_log_loss': round(validation_losses['smoothed_frequency'], 5),
            'candidate_log_loss': {k: round(v, 5) for k, v in validation_losses.items()},
            'test_log_loss': round(score(selected_test, y[test_train:, p]), 5),
            'test_uniform_log_loss': round(float(np.log(10)), 5)
        })
    # Select ONE complete model per draw session based on the correct
    # Exact/Any matching event, without consulting the untouched test segment.
    validation_box_losses = {kind: float(np.mean([
        box_log_loss(validation_candidates[i][kind], y[a:b])
        for i,(a,b) in enumerate(folds)
    ])) for kind in kinds}
    chosen_kind = min(kinds, key=lambda kind: validation_box_losses[kind])
    if validation_box_losses['smoothed_frequency'] - validation_box_losses[chosen_kind] < .005:
        chosen_kind = 'smoothed_frequency'
    output = [alternatives[chosen_kind][p] for p in range(3)]
    test_predictions = test_candidates[chosen_kind]
    selection = [chosen_kind] * 3
    test_truth = y[-test_n:]
    exact = {}
    for k in (1, 5, 10, 20):
        exact[f'top_{k}'] = round(top_hit(test_predictions, test_truth, k), 5)
    boxed = box_backtest(test_predictions, test_truth)
    chosen_exact_any = exact_any_picks(output)
    boxed['model'] = chosen_kind
    return {'draws': len(rows), 'last_draw': rows[-1][0].date().isoformat(),
            'recent': [''.join(map(str, ds)) for _, ds in rows[-40:][::-1]],
            'probabilities': output, 'model_probabilities': alternatives, 'validation': metrics,
            'exact_any_picks': chosen_exact_any,
            'exact_any_selection': {'model':chosen_kind, 'validation_box_log_loss':round(validation_box_losses[chosen_kind],5),
                                    'validation_baseline_log_loss':round(validation_box_losses['smoothed_frequency'],5),
                                    'test_box_log_loss':round(box_log_loss(test_predictions,test_truth),5),
                                    'candidate_box_log_loss':{k:round(v,5) for k,v in validation_box_losses.items()}},
            'holdout_draws': test_n, 'walkforward_folds': len(folds), 'selected_models': selection,
            'backtest': {'type': 'chronological unseen final test', 'draws': test_n,
                         'coverage': exact, 'straight': {'coverage': exact, 'fair_expected_coverage': {f'top_{k}':k/1000 for k in (1,5,10,20)}},
                         'box': boxed,
                         'uniform_expected_top_10': .01,
                         'mean_position_log_loss': round(float(np.mean(
                             [m['test_log_loss'] for m in metrics])), 5),
                         'uniform_position_log_loss': round(float(np.log(10)), 5)}}


def main():
    target = ROOT / 'web' / 'data' / 'predictions.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    previous = None
    if target.exists():
        try:
            previous = json.loads(target.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            previous = None

    # Check official data freshness BEFORE expensive feature extraction or model training.
    source_rows = {}
    for game in GAMES:
        url = BASE + f'pick3{game}.csv'
        req = urllib.request.Request(url, headers={'User-Agent': 'PICK3-AI/2.0'})
        with urllib.request.urlopen(req, timeout=40) as response:
            rows = parse(response.read().decode('utf-8-sig'), game)
        if not rows:
            raise ValueError(f'No usable official records: {game}')
        source_rows[game] = rows
        print('Official', game, len(rows), rows[-1][0].date(), flush=True)

    if previous and previous.get('schema_version') == 7:
        try:
            if all(previous['games'][g]['last_draw'] == source_rows[g][-1][0].date().isoformat()
                   and previous['games'][g]['recent'] == [
                       ''.join(map(str, digits)) for _, digits in source_rows[g][-40:][::-1]
                   ] for g in GAMES):
                print('No newly published official results. Skipping retraining.')
                return
        except (KeyError, TypeError, ValueError):
            pass

    payload = {'schema_version': 7, 'generated_at': datetime.now(timezone.utc).isoformat(),
               'source': BASE, 'games': {}}
    for game in GAMES:
        obj = predict_one(source_rows[game])
        obj['source_url'] = BASE + f'pick3{game}.csv'
        payload['games'][game] = obj
        print('Trained', game, obj['last_draw'], flush=True)

    live_path = target.parent / 'live_history.json'
    try:
        history = json.loads(live_path.read_text(encoding='utf-8')) if live_path.exists() else None
    except (ValueError, OSError):
        history = None
    new_history = reconcile(previous, payload, history)
    save_atomic(live_path, new_history)
    save_atomic(target, payload)
    print('Generated', target)


if __name__ == '__main__':
    main()
