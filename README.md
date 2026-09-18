<!--
README requirements (Repository Guide, "By MS4"):
  prediction · FTI diagram · clone-and-run steps · live URL · video link
Video link goes at the top. Every TODO must be gone by 2027-01-10.
-->

# optcg-match-forecast

> Predicts the winner of individual swiss-round matches in online One Piece TCG tournaments,
> from the two submitted decklists and each player's prior tournament history.

<!-- MS4: unlisted YouTube / SWITCHtube link here. No video files in the repo. -->
**Live system:** _TODO (MS4)_ · **Video (3 min):** _TODO (MS4)_

Semester project for **I.BA_MLOPS** (MLOps), BSc Artificial Intelligence & Machine Learning,
Hochschule Luzern — HS26.

---

## What it predicts

For every contested swiss pairing in an online tournament on
[play.limitlesstcg.com](https://play.limitlesstcg.com), the system emits
**P(player 1 wins)** at the moment that round's pairings publish. The match resolves within the
hour, so the label arrives on its own — a natural label, with no manual annotation anywhere in
the loop.

**Why this is hard, and why it is interesting:** strong players pick strong decks, so a naive
archetype win rate credits the *deck* for the *pilot*. Separating the two is the modelling
question — and out of time the per-player strength term turns out to contribute almost nothing
(Brier 0.2464 with it, 0.2465 without), while a random split makes it look essential. The signal
lives in archetype-vs-archetype matchup cells.

**The label is not derivable from the features.** It is the outcome of a game between two humans.
Player 1 wins 50.545% of 29,004 decided swiss matches — a Wilson CI of [49.97%, 51.12%], so seat
position is not distinguishable from a coin flip and carries no free signal.

**Success criterion.** Pooled **Brier ≤ 0.2490** against the coin-flip 0.2500, over ≥ 6 held-out
28-day windows (≥ 8,000 matches), with the 95% event-cluster bootstrap CI on the skill excluding
zero — plus calibration within 3 pp in every 5-pp favourite bucket with n ≥ 250.

An out-of-time reproduction of the existing model reaches Brier **0.2465** (skill +0.0035, CI
[+0.0023, +0.0047]) and **54.65%** accuracy. The edge is real but small — about 1.4% relative —
and the criterion is set where six months of real history says it holds, not where a single good
month says it could.

## Data

| | |
|---|---|
| Source | Limitless TCG tournament API (`play.limitlesstcg.com/api`) — keyless, community-run |
| Backfill on disk | 198 events · 29,807 pairings · 12,166 entrants · **11,575 with full 50-card decklists** (95.1%) |
| Usable matches | **29,004** decided swiss matches; 6,072 of them round 1 |
| Update | event-driven; new events are immutable once finished, so re-fetch by id is safe |

Ingest is deliberately polite: finished events are cached permanently because they never change,
and the request budget is throttled well inside the documented limit.

## Leakage

The API returns each entrant's decklist **directly alongside the event's own outcome**:

```jsonc
{ "player": "...", "decklist": {...}, "deck": {...},   // known before play — features
  "placing": 12, "record": {...}, "drop": null }       // outcomes OF THIS EVENT — never features
```

Two traps, both handled at the ingest boundary in
[`features/ingest.py`](src/optcg_forecast/features/ingest.py):

1. **Post-hoc fields.** `placing`, `record` and `drop` are stripped *physically* before anything
   downstream sees them — not filtered at training time, which would leave the footgun loaded for
   the next caller. `assert_no_leakage()` fails the pipeline if one ever survives.

2. **Selection on the outcome.** Players who drop out mid-event are **kept**. Dropping out is
   itself an outcome, and droppers win far fewer matches than finishers, so the obvious
   `WHERE placing IS NOT NULL` would condition the population on *finishing* and delete most of
   the true negatives. Measured on the backfill: **5,411 of 12,166 entrants (44.5%) dropped**, and
   **175 of them still received a placing** — so `drop IS NOT NULL` is the correct test, not
   `placing IS NULL`.

Splits are **out of time**, by event date, with events as the clustering unit for bootstrap
intervals. Matches from one event never straddle the split.

## Architecture

![FTI architecture](docs/src/architecture.png)

Three decoupled pipelines — they never call each other, only the feature store and the registry.

| | Pipeline | Trigger | Reads | Writes |
|---|---|---|---|---|
| 1 | **Feature** | GitHub Actions, hourly + on-demand backfill | Limitless API | Hopsworks |
| 2 | **Training** | scheduled / manual | Hopsworks feature view | MLflow registry |
| 3 | **Inference** | on pairing publication | registry + feature store | predictions / UI |

Regenerate the diagram after any stack change:

```bash
./scripts/build_diagram.sh
```

## Stack

| Concern | Choice | Why |
|---|---|---|
| Feature store | Hopsworks | point-in-time-correct joins — training and serving read one feature definition, so a player-history feature can never silently include the event being predicted |
| Tracking & registry | MLflow | aliased model versions: inference loads `models:/…@champion`, so promoting a model moves an alias instead of redeploying |
| Orchestration | GitHub Actions | scheduled pipelines live beside the code, and the runner stays the ingest edge rather than a cloud IP range |
| Serving | Google Cloud Run | container deploy, scales to zero between events |
| Storage | Google Cloud Storage | immutable partitioned landing zone for raw payloads, so features can always be rebuilt |

**Stretch, explicitly optional:** drift monitoring on decklist composition, a second tournament
feed to reduce organiser concentration, and calibration dashboards. Core FTI ships first.

## Clone and run

```bash
git clone https://github.com/kianakiser/optcg-match-forecast.git
cd optcg-match-forecast

uv sync                      # exact versions from uv.lock
cp .env.example .env         # then fill it in — see the table below

uv run python -m optcg_forecast.features.run                       # ingest + write features
uv run python -m optcg_forecast.features.backfill --start 2025-07-06 --end 2026-09-18
uv run python -m optcg_forecast.training.run                       # train, evaluate, register
uv run python -m optcg_forecast.inference.serve                    # serve predictions
```

Backfill runs through the **same** feature pipeline as live ingest — one code path, so a repaired
gap and a fresh event produce identical features.

With Docker:

```bash
docker build -t optcg-match-forecast .
docker run --rm --env-file .env -p 8080:8080 optcg-match-forecast
```

### Environment variables

Names only — see [`.env.example`](.env.example). Never commit `.env`; the same names must exist as
GitHub Actions secrets for the scheduled pipelines.

| Variable | What it is |
|---|---|
| `SOURCE_API_BASE_URL` / `SOURCE_API_KEY` | tournament API endpoint and key, if one is issued |
| `HOPSWORKS_API_KEY` / `HOPSWORKS_PROJECT` | feature store access |
| `MLFLOW_TRACKING_URI` / `MLFLOW_EXPERIMENT_NAME` | experiment tracking and registry |
| `GCP_PROJECT_ID` / `GCS_BUCKET` / `GCP_REGION` | serving and raw-payload storage |

## Tests

```bash
uv run pytest        # includes repo-hygiene checks that enforce the course rules
uv run ruff check .
```

The hygiene suite fails the build on the course's own rules: no `.env` tracked, no data or model
artifacts in git, no `mlruns/`, no secret patterns, no pipeline importing from a notebook.

## Layout

```
├── src/optcg_forecast/
│   ├── features/     ingest boundary, feature computation, backfill
│   ├── training/     train, evaluate out-of-time, register
│   ├── inference/    load champion, predict, serve
│   └── common/       config and the single source of feature definitions
├── docs/             proposal.pdf, ms*_summary.pdf, architecture diagram
├── tests/            unit tests, run in CI
├── scripts/          diagram generation
└── .github/workflows/  CI + scheduled pipelines
```

Feature definitions live in exactly one place under `common/`, used by both training and
inference. That is what keeps training–serving skew out.

## Milestones

| | Due | Status |
|---|---|---|
| MS1 Proposal | 2026-10-01 | ☐ |
| MS2 Feature pipeline | 2026-11-05 | ☐ |
| MS3 Training pipeline | 2026-12-03 | ☐ |
| MS4 Live system | 2027-01-10 | ☐ |

## Acknowledgements

Tournament data from the community-run [Limitless TCG](https://play.limitlesstcg.com) platform.
Non-commercial student project; One Piece Card Game is a trademark of its respective owner.
