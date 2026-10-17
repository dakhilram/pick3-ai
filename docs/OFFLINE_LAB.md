# PICK3 AI laptop model lab

The existing GitHub Actions workflow continues to check official Morning, Day, Evening and Night results and keeps the existing lightweight production model running. **The optional heavy lab is not scheduled on GitHub** and never changes the live website's predictions by itself.

## First-time laptop setup

Install Python 3.11 or later, Git, and a working C++ runtime compatible with LightGBM if required by your operating system.

```bash
git clone https://github.com/dakhilram/pick3-ai.git
cd pick3-ai
python -m venv .venv
```

On macOS/Linux: `source .venv/bin/activate`. On Windows PowerShell: `.venv\Scripts\Activate.ps1`.

```bash
python -m pip install -r requirements-heavy.txt
python -m unittest discover -s tests -v
python scripts/offline_lab.py
```

Run again when convenient:

```bash
git pull --ff-only
python scripts/offline_lab.py --sessions morning day evening night --test-draws 300
```

You can skip optional heavyweight models to save time:

```bash
python scripts/offline_lab.py --models frequency short_frequency random_forest gradient_boosting ensemble
```

The report is written to `reports/local_lab.json`. It compares candidate models on an earlier validation period, selects a winner without looking at final test outcomes, and separately measures **five exact/any tickets** on an untouched chronological test segment: exact matches, any-order matches (including exact), and fair-draw baselines. A short-term 120-draw frequency baseline is included. Optional XGBoost and LightGBM models are skipped with an explanation if not installed.

**Do not commit or replace the published `web/data/predictions.json` using the laptop report.** Validation performance can be noise. Test outcomes must not be used repeatedly to tune hyperparameters; once you iterate, use fresh untouched future draws for confirmation. The local report is a research comparison, not automatic model promotion. A separate reviewed integration would be needed to promote any winning approach. Five $1 tickets cost $5 per draw; hit rate is not profit, and there is no evidence of a dependable predictive edge in fair lotteries.

## Deployment design

- GitHub Pages: static display of published forecasts and live outcomes.
- GitHub Actions: routine official-result checks and lightweight daily retraining; laptop not required.
- Laptop: optional full model tournament, never needs GitHub-hosted heavy inference.
- To share a report, attach `reports/local_lab.json` to a GitHub issue or upload it in chat. Avoid overwriting production output without a separate audit.
