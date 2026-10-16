# PICK3 AI — Texas Pick 3

Mobile-friendly static web application plus a Python model evaluation/training pipeline using **official Texas Lottery CSV files**. Covers Morning, Day, Evening, and Night.

## Data and methods

The four CSV files come from [Texas Lottery's official downloads](https://www.texaslottery.com/export/sites/lottery/Games/Pick_3/Winning_Numbers/download.html). Each file has variable trailing historical columns; only the first seven columns are used (game name, month, day, year, three ordered digits). Date order and positional digit identity are preserved. FIREBALL is not modeled. Training uses the last 40 preceding draws to compute digit frequencies and lags, then fits a separate RandomForestClassifier for each position. The newest 20% of supervised examples are held out chronologically for an out-of-sample log-loss comparison against Laplace-smoothed digit frequencies from the training period. A model is selected only if its held-out log-loss beats that baseline. The chosen approach is refit using all history to produce next-draw candidate scores. This holdout is used for model selection, **not** an unbiased estimate of the final deployed ensemble; rigorous future assessment requires an untouched test period or walk-forward evaluation.

**Important:** Fair Pick 3 draws are independent and each exact-order combination has theoretical probability 1/1000. Historical regularities do not imply future predictability. Displayed model scores are *not calibrated winning probabilities*, and none of the proposed strategies has demonstrated an advantage. No wagering or payment functionality is included.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python scripts/train.py
python -m http.server 8000 --directory web
```

Open http://localhost:8000. Training downloads all four official CSVs; an internet connection is required.

## Publish to GitHub and access on any device

1. Create a new GitHub repository named `pick3-ai` (do not initialize with README). Then from this extracted directory:

   ```bash
   git init
   git add .
   git commit -m "Initial PICK3 AI application"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/pick3-ai.git
   git push -u origin main
   ```

2. In GitHub, open **Actions** and run **Update official draws and evaluate models** once. The Action writes `web/data/predictions.json`. For scheduled runs, GitHub Actions cron uses UTC; the schedule is nightly, not immediate post-draw.
3. Under **Settings → Pages**, set Source to **GitHub Actions**. Open Actions and run **Publish PICK3 AI to GitHub Pages** if necessary. Your site will be at `https://YOUR_USERNAME.github.io/pick3-ai/`.
4. Every new training result is committed to the repository, triggering a new deployment. GitHub Actions can be delayed or paused; stale data is marked with its final draw date on the dashboard.

If fetching fails, the Action fails rather than displaying fabricated data. No sample predictions are bundled intentionally.
