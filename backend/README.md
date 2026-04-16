# Backend README

## Overview

The backend is a FastAPI service for ingesting League of Legends match data, storing it in Postgres, computing derived analytics, and serving both rule-based and ML-assisted endpoints to the frontend.

Core responsibilities:

- ingest Riot account, match, draft, perk, and timeline data
- normalize raw match data into query-friendly relational tables
- precompute derived performance metrics such as KDA, CS/min, gold/min, kill participation, damage share, and vision/min
- expose analytics endpoints for players, matches, champions, teams, timelines, drafts, bans, and objective control
- train and serve ML models for playstyle clustering, win prediction, matchup prediction, regression, and early-game forecasting

This service is DB-first. Requests prefer local data whenever possible and only hit Riot live endpoints for ingestion or live team-analysis fallback paths.

## Stack

- FastAPI for the API layer
- SQLAlchemy for runtime DB access
- Prisma for schema management and migrations
- PostgreSQL or Supabase Postgres for storage
- httpx for Riot and Data Dragon HTTP access
- pandas, scikit-learn, xgboost, numpy, and joblib for ML pipelines
- slowapi for rate limiting

## Run Locally

### Prerequisites

- Python 3.11+
- Node.js 18+
- a PostgreSQL-compatible database URL
- a Riot developer API key

### Install

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
```

### Environment

Create `backend/.env` manually or run `./setup_env.sh`.

Required variables:

```env
DATABASE_URL=postgresql+psycopg://...
PRISMA_DATABASE_URL=postgresql://...
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
RIOT_API_KEY=...
```

Notes:

- `DATABASE_URL` is used by FastAPI and SQLAlchemy.
- `PRISMA_DATABASE_URL` is used by Prisma.
- `CORS_ORIGINS` is comma-separated and parsed into a list.
- Riot endpoints that enrich or ingest live data will fail without `RIOT_API_KEY`.

### Database

```bash
cd backend
npm run prisma:validate
npm run prisma:migrate:deploy
```

For local iteration on schema changes:

```bash
cd backend
npm run prisma:migrate:dev -- --name your_change_name
```

### Start the API

```bash
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Useful URLs:

- API docs: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/openapi.json
- Root probe: http://localhost:8000/

## Runtime Behavior

The app includes a few backend behaviors that matter operationally:

- champion and rune data from Data Dragon are preloaded on startup so champion-heavy endpoints do not pay first-request latency
- normal requests have a 60 second timeout
- backfill and matchup import routes get a 600 second timeout
- DB pool exhaustion and transient operational failures return structured `503` responses instead of generic `500`s
- ingestion routes are rate limited: single-player ingestion is `10/minute`, batch ingestion is `3/minute`
- unhandled errors are returned as structured JSON with `error`, `message`, and `path`

## Data Model

Main tables and what they store:

- `players`: Riot IDs, PUUIDs, region metadata
- `matches`: match metadata, patch, queue, platform, timestamps
- `participant_stats`: one row per player per match with raw performance stats
- `derived_metrics`: one row per player per match with normalized metrics used by analytics and ML
- `team_objectives`: team-level win/objective outcomes
- `team_bans`: draft bans by team and turn
- `draft_actions`: picks and bans in structured draft order
- `participant_perks`: rune paths, keystone, and shard selections
- `match_timelines`: one row per match for timeline metadata
- `timeline_participant_frames`: parsed per-frame economy/xp/position state
- `timeline_events`: structured timeline event records
- `champion_matchups`: imported researched matchup data from CSV sources such as Lolalytics, op.gg, or u.gg

## Backend Features

### Health and Diagnostics

- `GET /` returns a basic service probe
- `GET /health` returns API health
- `GET /health/db` verifies database connectivity
- `GET /db-test` performs a simple SQL round trip

### Ingestion

- `POST /ingest/player` ingests one Riot account and its recent ranked match history
- `POST /ingest/players/batch` ingests multiple players sequentially with per-player isolation

What ingestion stores immediately:

- player identity records
- match metadata
- participant stats
- team objectives
- team bans
- optional timeline data when `fetch_timeline=true`

What ingestion does not guarantee immediately:

- `derived_metrics`
- `draft_actions`
- `participant_perks`

Those are filled by backfill routes if needed.

### Backfills and Data Completion

- `POST /backfill/derived` computes missing derived metrics from already-stored match rows
- `GET /backfill/status` reports derived metric coverage
- `POST /backfill/draft-actions` re-fetches draft order for drafted matches
- `GET /backfill/draft-actions/status` reports draft coverage
- `POST /backfill/participant-perks` re-fetches runes and shard data
- `GET /backfill/participant-perks/status` reports perk coverage
- `POST /backfill/timeline` re-fetches timeline frames and events
- `GET /backfill/timeline/status` reports timeline coverage

The important design choice is that backfills are idempotent and mostly operate in bulk. Derived-metric backfill is entirely local and does not call Riot at all.

### Player and Match Retrieval

- `GET /players/` lists players with match counts and optional filtering
- `GET /players/{puuid}` returns one player by PUUID
- `GET /matches/player/{puuid}` returns recent match history with raw and derived stats
- `GET /matches/{match_id}` returns full match detail including participants, bans, objectives, and perks
- `GET /matches/{match_id}/draft` returns structured pick and ban order
- `GET /metrics/player/{puuid}` returns aggregate performance metrics across all stored matches

### Analytics

- ban analytics per player and per champion
- rune map and player rune summaries
- role-performance benchmarking versus peers in the same role
- rolling trends for charting and frontend summaries
- per-champion performance splits for a player
- objective-control splits between wins and losses

### Champion and Matchup Data

- `GET /champions` browses the full champion catalog with role, tag, and search filters
- `GET /champions/by-role/{role}` returns role-filtered champion lists
- `GET /champions/{champion_id}` returns one champion with Data Dragon metadata and tracked stats
- `GET /champions/matchup/{champ_a_id}/{champ_b_id}` returns matchup stats using researched rows when present, otherwise local ingested data
- `POST /matchups/import/csv` imports researched matchup CSV files
- `GET /matchups/` queries stored matchup rows
- `GET /matchups/{champion_id}/counters` returns champions that beat the selected champion
- `GET /matchups/{champion_id}/favors` returns champions the selected champion beats

### Timeline APIs

- `GET /timeline/{match_id}` returns timeline availability and row counts
- `GET /timeline/{match_id}/frames` returns parsed frame rows with pagination
- `GET /timeline/{match_id}/frames/by-puuid/{puuid}` resolves a player to the correct timeline slot and returns that player’s frames
- `GET /timeline/{match_id}/events` returns timeline events with cursor pagination

### Team Analysis

- `POST /teams/build` analyzes up to five players as a team
- `POST /teams/matchup` compares a blue and red roster and returns matchup edges plus win probability

These routes use a hybrid strategy:

- tracked players use local rolling stats from the DB
- untracked players fall back to live Riot fetches
- results are not persisted automatically

### AI and Model Management

Training endpoints:

- `POST /ai/train/playstyle`
- `POST /ai/train/win-prediction`
- `POST /ai/train/matchup-prediction`
- `POST /ai/train/kda-regression`
- `POST /ai/train/cs-regression`
- `POST /ai/train/early-game`
- `POST /ai/train/champion-clusters`

Inference and diagnostics:

- `GET /ai/models/status`
- `GET /ai/opponent-coverage`
- `GET /ai/threat-weights`
- `GET /ai/playstyle/{puuid}`
- `GET /ai/predict/{puuid}/{match_id}`
- `GET /ai/predict/kda/{puuid}/{match_id}`
- `GET /ai/predict/cs/{puuid}/{match_id}`
- `GET /ai/champions/{puuid}`
- `GET /ai/backtest/win-prediction`
- `GET /ai/early-game/{match_id}`
- `POST /ai/enrich/opponent-features`

## How the Algorithms Work

### 1. Derived Metrics

The backend computes a normalized feature row per player per match in `derived_metrics`.

Formulas:

- `KDA = (kills + assists) / max(deaths, 1)`
- `CS/min = (lane minions + jungle minions) / game_minutes`
- `gold/min = gold_earned / game_minutes`
- `vision/min = vision_score / game_minutes`
- `kill_participation = (kills + assists) / team_kills`
- `damage_share = player_damage_to_champions / team_damage_to_champions`

Edge-case handling is explicit:

- zero deaths are clamped with `max(deaths, 1)`
- zero-duration games yield `0.0` for per-minute metrics
- teams with zero kills or zero damage yield `0.0` for participation and share metrics

These metrics are the backbone for analytics, champion summaries, and ML training.

### 2. Rolling Feature Extraction

Most ML routes do not learn directly from raw match rows. They learn from rolling features built from a player’s prior ranked solo games only.

Important rules:

- queue is restricted to `420` by default for competitive consistency
- features are strictly prior to the target match to prevent leakage
- missing numeric values are median-imputed
- patch versions are converted into sortable floats
- roles are encoded numerically for model input

Examples of rolling features:

- `win_rate_20`
- `avg_kda_20`
- `avg_cs_per_min_20`
- `avg_gold_per_min_20`
- `avg_kill_part_20`
- `win_streak`
- `death_rate_20`
- `vision_per_min_20`
- `kda_std_10`
- `cs_trend_10`
- `avg_role_norm_kda_20`

`avg_role_norm_kda_20` is a role-normalized KDA signal. It lets the backend compare players relative to the expectations of their role instead of treating all roles the same.

### 3. Champion Recommendation Scoring

Champion recommendations are not a direct supervised ML prediction. They are a composite score built from per-champion aggregates and playstyle affinity.

Signals in the score:

- Bayesian-smoothed win rate so tiny sample sizes do not dominate
- KDA efficiency
- role-aware CS/min normalization
- player experience on the champion
- recency weighting
- optional playstyle-to-role affinity boost from the playstyle cluster

The outcome is a ranked list that prefers champions the player performs well on while still discounting noisy small-sample picks.

### 4. Playstyle Clustering

`playstyle_kmeans.joblib` is trained with KMeans on aggregated player-level features.

Training pipeline:

- require at least 20 players with 10 or more matches each
- standardize features with `StandardScaler`
- fit `KMeans(n_clusters=4)`
- compute silhouette score and inertia
- inverse-transform centroids back into human-readable feature space
- auto-label clusters based on centroid signal patterns

Current archetype labels:

- `carry`
- `skirmisher`
- `support_utility`
- `farm_efficiency`

Cluster labels are not hardcoded by cluster index. The service examines centroid strengths and assigns labels based on which cluster most strongly expresses each archetype’s primary and secondary signals.

### 5. Win Predictor

`win_predictor.joblib` is a per-player match outcome model.

How it trains:

- use rolling pre-match features only
- sort rows by match time
- split oldest 80% for training and newest 20% for testing
- train both Logistic Regression and XGBoost
- pick the better model by ROC-AUC
- store medians for inference-time imputation

Important feature groups:

- personal rolling stats
- team average rolling stats
- opponent average rolling stats when available
- differential features such as `win_rate_diff`, `kda_diff`, and `cs_diff`
- side bias via `blue_side`

Why this matters: it is designed to answer “given what this player and surrounding context looked like before the match, how likely was a win?” without ever peeking at target-match outcomes.

### 6. Matchup Predictor

`matchup_predictor.joblib` is a match-level team-vs-team predictor. This is different from the per-player win predictor.

One row equals one match, from team 100’s perspective.

Features include:

- team 100 absolute rolling averages
- team 200 absolute rolling averages
- team differentials such as win-rate, KDA, CS, gold, vision, kill participation, and role-normalized KDA
- tracked-player coverage counts
- patch context

This model usually has a stronger conceptual signal than the per-player model because it can see both sides of the matchup explicitly.

### 7. KDA and CS Regression

The backend trains two separate regressors:

- `kda_regressor.joblib`
- `cs_regressor.joblib`

Both reuse the same leakage-safe rolling feature pattern but predict continuous targets instead of win/loss.

Training behavior:

- baseline model is Ridge regression
- production candidate is XGBoost regressor
- selection is based on $R^2$
- RMSE and MAE are also reported

`win_rate_20` and `win_streak` are intentionally excluded from the shared regression feature set because they encode match-outcome information too directly for the target being predicted.

### 8. Early-Game Predictor

`earlygame_predictor.joblib` predicts whether team 100 wins using timeline-derived state at 10 and 15 minutes.

Features come from parsed timeline frames and events:

- gold diff at 10 and 15
- XP diff at 10 and 15
- level diff at 10
- CS diff at 10
- first blood team
- first tower team
- first dragon team

The model is logistic regression only. The design favors interpretability over model complexity because the feature set is compact and directly tied to early-game state.

This model only works for matches ingested with `fetch_timeline=true` or backfilled later.

### 9. Champion Clustering

`champion_clusters.joblib` clusters champions by their observed aggregate tracked performance profile.

Champion-level features:

- average KDA
- average CS/min
- average gold/min
- average kill participation
- average vision/min
- average damage share

The output is a coarse archetype assignment such as:

- `farm_carry`
- `skirmisher`
- `utility`
- `versatile`

This artifact is later used to connect player playstyle clusters to champion recommendation logic.

### 10. Threat Scoring and Team DNA

Team analysis uses a mix of learned signals and hand-tuned heuristics.

Threat score is a 0 to 10 composite built from:

- normalized win rate
- normalized KDA or role-normalized KDA when available
- confidence bonus based on number of games in the window

If the win predictor has a trusted AUC of at least `0.60`, the weights for win rate and KDA are derived from model feature importances. Otherwise the service falls back to defaults.

Team DNA is then inferred from the roster’s playstyle mix, while composition heuristics inspect:

- role coverage
- CS profile
- average win rate
- champion tags
- native versus flex versus off-meta role fit

`/teams/matchup` adds per-role head-to-head cards and uses the trained matchup model when available, otherwise a rule-based weighted comparison.

## Model Artifacts Reported by `/ai/models/status`

The status endpoint currently reports all known backend model artifacts:

- `playstyle_kmeans`
- `win_predictor`
- `matchup_predictor`
- `kda_regressor`
- `cs_regressor`
- `earlygame_predictor`
- `champion_clusters`

For trained models it returns:

- `trained`
- `trained_at`
- `n_samples`
- `metrics`
- `model_type`

For missing models it returns the training route to call next.

## Testing

Run backend tests:

```bash
cd backend
source .venv/bin/activate
pytest
```

Notes:

- integration tests use in-memory SQLite for smoke coverage
- some AI and raw-SQL tests are marked PostgreSQL-only because SQLite cannot execute PostgreSQL-specific syntax such as `ANY(...)`, casts, or window-heavy queries

## File Map

- `app/main.py`: FastAPI app setup, middleware, startup preload, and exception handlers
- `app/api/routes/`: route modules grouped by feature area
- `app/services/feature_extractor.py`: rolling and training feature generation
- `app/services/ai_service.py`: model training, inference, and team-analysis logic
- `app/services/ingestion_service.py`: Riot ingestion pipeline
- `app/services/riot_client.py`: Riot API wrapper with retries and backoff
- `app/services/riot_live_service.py`: DB-first, Riot-fallback live stat fetches for team analysis
- `app/services/ddragon.py`: cached champion and rune metadata
- `prisma/schema.prisma`: database schema definition
- `ml_models/`: trained model artifacts and metadata sidecars

## Suggested Workflow

1. Ingest tracked players with `POST /ingest/player`.
2. Run backfills for `derived_metrics`, `participant_perks`, `draft_actions`, and `timeline` as needed.
3. Train the AI models once there is enough data.
4. Use `/ai/models/status` to confirm artifact readiness.
5. Consume analytics, recommendation, and team-analysis routes from the frontend.