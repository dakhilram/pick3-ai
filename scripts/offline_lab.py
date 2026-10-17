"""Optional laptop-only model tournament. Does not overwrite production forecasts.

Run: python scripts/offline_lab.py --sessions morning day --test-draws 300
Requires internet for official Texas Lottery CSV downloads.
"""
import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

from train import (BASE, WINDOW, build, parse, frequency, full_prob,
                   make_model, normalize, box_log_loss, exact_any_backtest)

SESSIONS = ("morning", "day", "evening", "night")
CANDIDATES = ("frequency", "short_frequency", "random_forest",
              "gradient_boosting", "ensemble", "xgboost", "lightgbm")


def fit_predict(kind, X, y, X_out, *, seed=42):
    """Return one 10-class probability matrix for each ordered digit position."""
    results = []
    for pos in range(3):
        if kind in ("frequency", "short_frequency"):
            subset = y[:, pos] if kind == "frequency" else y[-120:, pos]
            results.append(np.tile(frequency(subset), (len(X_out), 1)))
            continue
        if kind == "ensemble":
            parts = [fit_predict(n, X, y, X_out, seed=seed)[pos]
                     for n in ("frequency", "random_forest", "gradient_boosting")]
            results.append(normalize(np.mean(parts, axis=0)))
            continue
        if kind in ("random_forest", "gradient_boosting"):
            model = make_model(kind, seed + pos)
        elif kind == "xgboost":
            from xgboost import XGBClassifier
            model = XGBClassifier(n_estimators=120, max_depth=3, learning_rate=.045,
                                  subsample=.85, colsample_bytree=.85, n_jobs=2,
                                  objective="multi:softprob", random_state=seed + pos)
        elif kind == "lightgbm":
            from lightgbm import LGBMClassifier
            model = LGBMClassifier(n_estimators=120, max_depth=4,
                                   learning_rate=.045, num_leaves=12, verbosity=-1,
                                   n_jobs=2, random_state=seed + pos)
        else:
            raise ValueError(kind)
        model.fit(X, y[:, pos])
        results.append(full_prob(model, X_out))
    return results


def tournament(rows, candidates, test_draws=300, validation_draws=300):
    """Select on chronological validation ONLY; report separate untouched test."""
    if len(rows) < WINDOW + test_draws + validation_draws + 350:
        raise ValueError("Insufficient official draw history for chronological holdout")
    X, y = build(rows[-(WINDOW + 2400):])
    cutoff = len(X) - test_draws
    validation_start = cutoff - validation_draws
    if validation_start < 350:
        raise ValueError("Insufficient model-training rows")
    available = {}
    unavailable = {}
    for kind in candidates:
        try:
            prob = fit_predict(kind, X[:validation_start], y[:validation_start],
                               X[validation_start:cutoff])
            available[kind] = {"validation_loss":box_log_loss(prob, y[validation_start:cutoff])}
        except ImportError as e:
            unavailable[kind] = str(e)
    if "frequency" not in available:
        raise ValueError("frequency baseline is required")
    winner = min(available, key=lambda k: available[k]["validation_loss"])
    # Prefer simpler baseline if advantage is too small to trust.
    if available["frequency"]["validation_loss"] - available[winner]["validation_loss"] < .005:
        winner = "frequency"
    for kind in available:
        prob = fit_predict(kind, X[:cutoff], y[:cutoff], X[cutoff:])
        available[kind]["test_loss"] = round(box_log_loss(prob, y[cutoff:]), 5)
        available[kind]["test_tickets"] = exact_any_backtest(prob, y[cutoff:])
        available[kind]["validation_loss"] = round(available[kind]["validation_loss"], 5)
    return {"selected_on_validation":winner, "draws_tested":test_draws,
            "models":available, "skipped_optional_models":unavailable,
            "selection_note":"Test scores are never used for selection. Test comparisons are exploratory and not guaranteed future performance."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", nargs="+", choices=SESSIONS, default=list(SESSIONS))
    parser.add_argument("--models", nargs="+", choices=CANDIDATES, default=list(CANDIDATES))
    parser.add_argument("--test-draws", type=int, default=300)
    parser.add_argument("--validation-draws", type=int, default=300)
    parser.add_argument("--output", default="reports/local_lab.json")
    args = parser.parse_args()
    if args.test_draws < 100 or args.validation_draws < 100:
        parser.error("Both periods must have at least 100 draws")
    models = list(dict.fromkeys(["frequency"] + args.models))
    output = {"created_at":datetime.now(timezone.utc).isoformat(),
              "play":"Five Exact/Any $1 tickets; no Fireball",
              "source":BASE, "sessions":{}}
    for session in args.sessions:
        req=urllib.request.Request(BASE + f"pick3{session}.csv",
                                   headers={"User-Agent":"PICK3-AI-offline-lab/1.0"})
        with urllib.request.urlopen(req, timeout=50) as resp:
            rows=parse(resp.read().decode("utf-8-sig"),session)
        print("Evaluating",session,"with",len(rows),"official draws",flush=True)
        output["sessions"][session]=tournament(rows,models,args.test_draws,args.validation_draws)
        winner=output["sessions"][session]["selected_on_validation"]
        print(session,"winner:",winner,"test:",output["sessions"][session]["models"][winner]["test_tickets"],flush=True)
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(output,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print("Wrote report:",path)


if __name__ == "__main__":
    main()
