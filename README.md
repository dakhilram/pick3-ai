# Pick3 AI V2

Static Texas Pick 3 research dashboard: [live site](https://dakhilram.github.io/pick3-ai/).

The production updater is `scripts/v2.py`. It reads the four [official Texas Lottery CSV archives](https://www.texaslottery.com/export/sites/lottery/Games/Pick_3/Winning_Numbers/download.html). A single lightweight positional-frequency engine scores all 1,000 ordered three-digit results. Recent global history forms a shared prior; each session adds a smaller adjustment. For Any Order, it sums the masses of distinct permutations and publishes ten unique groups per session. Exact, Any Order, Exact/Any, and Combo are interpretations of those same outcomes.

Draws are scheduled Monday–Saturday at 10:00 a.m., 12:27 p.m., 6:00 p.m., and 10:12 p.m. America/Chicago. The first scheduled checks are six minutes after each draw, with retries. GitHub Actions may start late, and official results may appear late. A row is processed only after its scheduled drawing and only when it is present in the official archive.

`web/data/predictions.json` is the single atomic publication. It contains the latest forecasts, every V2 publication snapshot, verified results, walk-forward historical rates, and forward rates. The updater scores the latest snapshot published before a draw, then generates fresh forecasts for all four sessions. Repeated runs with no new official draw leave the file unchanged. Previously published snapshots are retained unchanged.

Model probabilities are uncalibrated estimates. Fair-random benchmarks count the distinct ordered outcomes covered by each Any Order group. Historical walk-forward testing and actual published forward testing are labeled separately. No predictive advantage over fair independent draws is claimed.

The legacy `scripts/train.py` and `scripts/live_tracker.py` remain in the repository because older tests and the separate laptop backend may still depend on them. Neither is called by the V2 updater or dashboard. `scripts/package_site.py` publishes only active V2 assets and `predictions.json`; older data files remain in the repository as archives and are excluded from the deployed site.

## Verify locally

```text
python -m unittest discover -s tests -p test_v2.py -v
node --check web/app.js
python -m json.tool web/data/predictions.json
```

On Windows, Python's `zoneinfo` needs an installed IANA time-zone database, such as the `tzdata` package. GitHub's Ubuntu runner supplies one. Run `python scripts/v2.py` to check the official archives and publish new data. Serve `web/` as a static site to view the dashboard.
