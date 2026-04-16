# Esports Analytics Platform

This repository is a full-stack League of Legends analytics system with:

- a Next.js frontend for dashboards and analysis views
- a FastAPI backend for ingestion, analytics, and ML training/inference
- PostgreSQL/Supabase persistence for player, match, draft, perk, and timeline data

It is designed to support:

- live and historical player analysis
- team composition and matchup analysis
- champion recommendation and matchup intelligence
- ML-backed prediction endpoints

## 1. Architecture at a Glance

Data flow:

1. Frontend sends user actions to backend APIs.
2. Backend ingests Riot data and normalizes it into relational tables.
3. Backfill jobs complete missing derived fields and timeline/rune/draft coverage.
4. Feature extraction services build rolling windows and team differential features.
5. ML endpoints train model artifacts into backend/ml_models.
6. Inference endpoints serve predictions and analytics back to the frontend.

Main subsystems:

- frontend: UI, routing, API clients
- backend API routes: ingestion, analytics, backfill, AI, teams, champions, timelines
- backend services: Riot client, feature extraction, metric calculators, ML pipelines
- database schema: Prisma-managed PostgreSQL model

## 2. Repository Structure

```text
capstone-esports/
├── frontend/
│   ├── src/
│   ├── package.json
│   └── README.md
├── backend/
│   ├── app/
│   │   ├── api/routes/
│   │   ├── services/
│   │   ├── models/
│   │   ├── db/
│   │   └── main.py
│   ├── prisma/
│   │   ├── schema.prisma
│   │   └── migrations/
│   ├── ml_models/
│   ├── requirements.txt
│   └── README.md
├── docs/
├── benchmark.sh
├── test_api.sh
├── performance_evidence.md
└── README.md
```

## 3. Prerequisites

- Python 3.11+
- Node.js 18+
- npm
- PostgreSQL-compatible database (Supabase supported)
- Riot Developer API key
- jq (optional but useful for test scripts)

## 4. Environment Configuration

### Backend environment

Create backend/.env with at least:

```env
DATABASE_URL=postgresql+psycopg://...
PRISMA_DATABASE_URL=postgresql://...
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
RIOT_API_KEY=your_riot_key
```

Notes:

- DATABASE_URL is consumed by FastAPI/SQLAlchemy.
- PRISMA_DATABASE_URL is consumed by Prisma.
- CORS_ORIGINS supports a comma-separated list.

### Frontend environment

Create frontend/.env.local:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Without this, frontend API calls will point to the wrong backend base URL.

## 5. Setup and Run

### Step A: Backend setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
```

Optional guided env setup:

```bash
./setup_env.sh
```

### Step B: Apply DB migrations

```bash
cd backend
npm run prisma:validate
npm run prisma:migrate:deploy
```

### Step C: Start backend only

```bash
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs should be available at http://localhost:8000/docs.

### Step D: Start frontend only

```bash
cd frontend
npm install
npm run dev
```

Frontend should be available at http://localhost:3000.

### Step E: Start backend + frontend together

From frontend, the repo already includes combined scripts:

```bash
cd frontend
npm run dev:all
```

If port 8000 is stuck from a previous run:

```bash
cd frontend
npm run dev:fresh
```

## 6. Core Backend Capability Map

### Health and status

- GET /
- GET /health
- GET /health/db
- GET /db-test

### Ingestion

- POST /ingest/player
- POST /ingest/players/batch

### Backfills

- POST /backfill/derived
- GET /backfill/status
- POST /backfill/draft-actions
- GET /backfill/draft-actions/status
- POST /backfill/participant-perks
- GET /backfill/participant-perks/status
- POST /backfill/timeline
- GET /backfill/timeline/status

### Player and match retrieval

- GET /players/
- GET /players/{puuid}
- GET /matches/player/{puuid}
- GET /matches/{match_id}
- GET /matches/{match_id}/draft
- GET /metrics/player/{puuid}

### Analytics

- bans, runes, role performance, trends, champion splits, objective control
- endpoints under /analytics

### Champion and matchup intelligence

- endpoints under /champions and /matchups
- supports both ingested matchup inference and researched matchup CSV imports

### Timeline analysis

- endpoints under /timeline for summary, frames, and event streams

### Team analysis

- POST /teams/build
- POST /teams/matchup

### AI and ML

- training, inference, and diagnostics under /ai
- model status endpoint: GET /ai/models/status

## 7. ML Models in This Project

Current backend artifacts include:

- playstyle_kmeans
- win_predictor
- matchup_predictor
- kda_regressor
- cs_regressor
- earlygame_predictor
- champion_clusters

Training is initiated via POST routes under /ai/train/*.
Inference is served via GET routes under /ai/* and /teams/matchup.

Important lifecycle guidance:

1. Ingest players first.
2. Backfill derived fields and timeline/perk/draft data as needed.
3. Train models once sample size thresholds are met.
4. Verify readiness with /ai/models/status.

## 8. Typical Developer Workflow

### Initial project boot

1. configure backend env
2. migrate DB
3. run backend
4. run frontend

### Populate data

1. call POST /ingest/player with one or more tracked players
2. run backfill endpoints for complete feature coverage
3. check /backfill/status and related status routes

### Enable AI features

1. train required AI models through /ai/train/*
2. confirm model artifacts via /ai/models/status
3. consume prediction and recommendation endpoints

## 9. Testing and Validation

### Backend tests

```bash
cd backend
source .venv/bin/activate
pytest
```

### Basic API smoke script

```bash
./test_api.sh
```

### Benchmark and performance evidence

```bash
./benchmark.sh http://localhost:8000
```

This updates performance_evidence.md with:

- derived metric coverage
- endpoint timing checks
- player count checks
- storage scale indicators

## 10. Troubleshooting

### Frontend loads but API calls fail

- verify frontend/.env.local contains NEXT_PUBLIC_API_URL
- confirm backend is running on the same URL and port
- verify CORS_ORIGINS includes the frontend origin

### Riot ingestion fails

- verify RIOT_API_KEY is set and still valid
- verify platform and tagLine values are correct
- retry if Riot rate limits return 429

### Model endpoints show untrained

- run the corresponding /ai/train/* endpoint
- verify artifact presence through GET /ai/models/status

### Slow endpoint responses

- run benchmark.sh to identify bottlenecks
- check DB health and indexes
- check data volume and endpoint query scope

## 11. Documentation Index

- complete backend guide: [backend/README.md](backend/README.md)
- backend schema: [backend/prisma/schema.prisma](backend/prisma/schema.prisma)
- retraining checklist: [docs/retraining-checklist.md](docs/retraining-checklist.md)
- performance evidence report: [performance_evidence.md](performance_evidence.md)
- benchmark script: [benchmark.sh](benchmark.sh)
- API smoke test script: [test_api.sh](test_api.sh)

## 12. One-Command Local Development

If backend dependencies are installed and backend/.env is configured:

```bash
cd frontend
npm run dev:all
```

This starts:

- backend on port 8000
- frontend on port 3000

## 13. Algorithm Deep Dive (Backend)

This section expands the core algorithm behavior used by the backend services.

### 13.1 Derived Metric Computation

The backend computes one normalized derived row per player per match before most analytics and ML steps.

Primary formulas:

- KDA = (kills + assists) / max(deaths, 1)
- CS_per_min = (total_minions_killed + neutral_minions_killed) / game_minutes
- Gold_per_min = gold_earned / game_minutes
- Vision_per_min = vision_score / game_minutes
- Kill_participation = (kills + assists) / team_kills
- Damage_share = player_damage_to_champions / team_damage_to_champions

Stability guards:

- if game duration is 0, all per-minute metrics become 0.0
- if team_kills is 0, kill participation becomes 0.0
- if team_damage is 0, damage share becomes 0.0

Why it matters:

- these normalized features remove match-length bias and are reused by analytics, recommendation scoring, and model training

### 13.2 Rolling Feature Engineering

The feature extractor builds pre-match rolling windows from ranked solo queue data only.

Rules enforced in the pipeline:

- queue filter defaults to 420 for competitive consistency
- target match is excluded by time cutoff, so only strictly prior games are used
- missing numeric values are filled with medians
- patch strings are converted to sortable floats (example: 14.10.1 -> 14.10)
- roles are encoded numerically

Representative rolling features:

- win_rate_20
- avg_kda_20
- avg_cs_per_min_20
- avg_gold_per_min_20
- avg_kill_part_20
- win_streak
- death_rate_20
- vision_per_min_20
- kda_std_10
- cs_trend_10
- avg_role_norm_kda_20

Key calculations:

- win_streak: consecutive prior wins or losses (positive for win streak, negative for loss streak)
- kda_std_10: standard deviation of recent KDA values (consistency signal)
- cs_trend_10: least-squares slope of CS/min over recent games (improving or declining farm trend)

### 13.3 Champion Recommendation Algorithm

Champion recommendations are score-based, not single-model classification.

Signals combined in scoring:

- Bayesian-smoothed win rate (small-sample shrinkage toward neutral prior)
- KDA efficiency
- role-aware CS normalization caps
- experience weighting by games played on champion
- recency weighting using timestamp decay
- optional playstyle-cluster affinity boost

Design intent:

- prevent one or two lucky games from dominating rank
- favor sustained performance and stable champion mastery

### 13.4 Playstyle Clustering

Model: KMeans over aggregated player profiles.

Training process:

1. Require minimum sample gate (players with enough games).
2. Standardize feature space with StandardScaler.
3. Fit KMeans with four clusters.
4. Evaluate silhouette score and inertia.
5. Inverse-transform centroids for interpretability.
6. Auto-label cluster IDs by centroid signal dominance.

Auto-labeled archetypes:

- carry
- skirmisher
- support_utility
- farm_efficiency

The auto-label stage avoids hardcoding cluster index semantics and makes labels robust across retrains.

### 13.5 Win Prediction Model

Goal: estimate per-player pre-match win probability.

Training mechanics:

- candidate models: Logistic Regression and XGBoost classifier
- temporal split: oldest 80% train, newest 20% test
- model selection by ROC-AUC
- save training medians for inference-time imputation parity

Feature groups:

- personal rolling stats
- team aggregate rolling stats
- opponent aggregate rolling stats when available
- differential features (win_rate_diff, kda_diff, cs_diff, gold_diff_norm)
- contextual feature (blue_side)

Leakage protection:

- no current-match stats are allowed into training row features
- all features represent pre-match state only

### 13.6 Matchup Prediction Model

Goal: estimate team-100 win probability at match level.

Unlike per-player win prediction, each row here is one full match with both team contexts.

Feature structure:

- team 100 absolute rolling averages
- team 200 absolute rolling averages
- direct team differentials (KDA, CS, gold, vision, kill participation, role-normalized KDA)
- tracked-player coverage and patch context

Training strategy:

- compare Logistic Regression baseline against XGBoost
- choose by ROC-AUC
- persist best model artifact and feature metadata

Why often stronger:

- explicitly models relative strength between both teams instead of isolated player history

### 13.7 Regression Models (KDA and CS/min)

Two dedicated regressors are trained:

- kda_regressor
- cs_regressor

Shared design:

- candidate models: Ridge and XGBoost regressor
- temporal split (80/20)
- choose by R^2
- report RMSE and MAE for error magnitude

Feature hygiene:

- win_rate_20 and win_streak are excluded in regression training set because they inject target-correlated outcome information too directly

### 13.8 Early-Game Predictor

Goal: predict final winner from minute-10/minute-15 state.

Inputs:

- gold diff, xp diff, level diff, cs diff
- first blood team, first tower team, first dragon team

Model:

- Logistic Regression (interpretable coefficients)

Training gates:

- requires timeline-backed matches
- uses temporal split
- stores coefficients as explainable feature contributions

Constraint:

- match must include timeline data (ingested with fetch_timeline=true or backfilled)

### 13.9 Champion Archetype Clustering

Goal: group champions by observed stat profile in tracked data.

Inputs include:

- avg_kda
- avg_cs_per_min
- avg_gold_per_min
- avg_kill_participation
- avg_vision_per_min
- avg_damage_share

Output labels are archetype-like groups such as farm_carry, skirmisher, utility, and versatile.

This artifact supports role- and playstyle-aware recommendation logic.

### 13.10 Threat Score and Team DNA

Threat score is a bounded composite on a 0-10 scale.

Base equation:

- wr_component = min(win_rate, 1.0) * wr_weight
- kda_component = min(kda / 8.0, 1.0) * kda_weight
- confidence_component = min(games / 20.0, 1.0) * 2.0
- threat_score = wr_component + kda_component + confidence_component

Weight source behavior:

- if win predictor AUC >= 0.60, wr_weight and kda_weight are derived from model feature importances (budgeted to 8 total points)
- otherwise defaults are used (4.0, 4.0)

Team DNA and composition analysis then combine:

- playstyle cluster distribution
- role coverage
- champion-tag composition heuristics
- role-fit labels (native, flex, off-meta)

### 13.11 Role Matchup Card Logic

In team matchup analysis, each role lane card compares blue vs red using weighted composites.

Composite used in cards:

- 45% win-rate signal
- 35% KDA signal (role-normalized KDA when available)
- 20% CS/min signal

Output includes:

- edge winner per role
- metric-level deltas
- role-context interpretation when z-score normalization is present

### 13.12 Evaluation and Model Governance

The backend includes practical model governance mechanics:

- minimum data gates before training starts
- temporal validation instead of random shuffle
- persisted train medians for inference consistency
- model metadata sidecars for auditability
- model status endpoint for deployment readiness checks

Endpoint for runtime audit:

- GET /ai/models/status reports trained state, trained_at timestamp, sample count, metrics, and model type for each artifact

### 13.13 Exact Feature Inventories by Model

This subsection lists the feature columns as implemented in backend services today.

Win predictor features:

- win_rate_20
- avg_kda_20
- avg_cs_per_min_20
- avg_gold_per_min_20
- avg_kill_part_20
- win_streak
- death_rate_20
- vision_per_min_20
- kda_std_10
- cs_trend_10
- team_avg_win_rate_20
- team_avg_kda_20
- team_avg_cs_min_20
- team_gold_diff_prior
- patch_version_float
- role_encoded
- avg_role_norm_kda_20
- opp_avg_win_rate_20
- opp_avg_kda_20
- opp_avg_cs_min_20
- win_rate_diff
- kda_diff
- cs_diff
- gold_diff_norm
- blue_side

Regression feature set shared by KDA and CS/min models:

- avg_kda_20
- avg_cs_per_min_20
- avg_gold_per_min_20
- avg_kill_part_20
- death_rate_20
- vision_per_min_20
- kda_std_10
- cs_trend_10
- team_avg_win_rate_20
- team_avg_kda_20
- team_avg_cs_min_20
- team_gold_diff_prior
- patch_version_float
- role_encoded
- avg_role_norm_kda_20
- opp_avg_win_rate_20
- opp_avg_kda_20
- opp_avg_cs_min_20

Matchup predictor features:

- t100_win_rate_20
- t100_avg_kda_20
- t100_avg_cs_per_min_20
- t100_avg_gold_per_min_20
- t100_vision_per_min_20
- t100_avg_kill_part_20
- t100_avg_role_norm_kda_20
- t200_win_rate_20
- t200_avg_kda_20
- t200_avg_cs_per_min_20
- t200_avg_gold_per_min_20
- t200_vision_per_min_20
- win_rate_diff
- kda_diff
- cs_diff
- gold_diff
- vision_diff
- kill_part_diff
- role_norm_kda_diff
- patch_version_float
- t100_tracked
- t200_tracked

Timeline model features:

- gold_diff_10
- xp_diff_10
- level_diff_10
- cs_diff_10
- gold_diff_15
- xp_diff_15
- first_blood_team
- first_tower_team
- first_dragon_team

Playstyle clustering features:

- avg_kda
- avg_cs_per_min
- avg_gold_per_min
- avg_kill_participation
- avg_damage_share
- avg_vision_per_min
- avg_kills
- avg_deaths
- avg_assists
- avg_wards_placed
- avg_vision_score
- first_blood_rate
- physical_dmg_pct
- magic_dmg_pct

### 13.14 Data Gates and Split Policy

Training starts only if minimum data criteria are met:

- playstyle clustering: at least 20 eligible players with 10+ matches each
- win predictor: at least 100 labeled training rows
- KDA regressor: at least 100 labeled rows
- CS regressor: at least 100 labeled rows
- early-game predictor: at least 50 timeline matches
- matchup predictor: at least 50 unique matches

Temporal validation policy (consistent across predictive models):

- sort by time order
- use first 80 percent for train
- use latest 20 percent for test
- reject training run if test set has only one class for classification models

Why this matters:

- prevents optimistic leakage from random shuffles in time-dependent data
- better approximates production prediction where future data is unknown

### 13.15 Imputation and Neutral Priors

The backend does not use a naive fill-zero policy for all missing values.

Imputation strategy:

- compute train medians on the training dataframe
- persist medians in artifact metadata
- reuse the same medians at inference time for strict train/serve parity

Neutral fallback priors are used when some columns are all-NaN:

- opp_avg_win_rate_20 -> 0.5
- opp_avg_kda_20 -> 2.5
- opp_avg_cs_min_20 -> 7.0
- differential features -> 0.0 (assume no edge)

This avoids injecting unrealistic bias such as assuming unknown opponents have 0 percent win rate.

### 13.16 End-to-End Training Pseudocode

Win predictor training pseudocode:

```text
df = get_all_rolling_features_bulk(db)
if len(df) < 100: stop
df = drop rows without win label
df = sort by game_creation ascending
for each feature col:
	median[col] = median(df[col]) or neutral_fallback[col]
	df[col] = fill_na(df[col], median[col])
X = df[feature_cols]
y = df[win]
split = int(0.8 * len(X))
train = X[:split], y[:split]
test = X[split:], y[split:]
train logistic + xgboost
evaluate ROC-AUC on test
select best model by AUC
save artifact + medians + metrics + top factors
```

Regression training pseudocode:

```text
df = get_all_rolling_features_bulk(db)
attach target column (kda or cs_per_min)
if labeled rows < 100: stop
sort by game_creation
median-impute feature columns
split 80/20 chronologically
train Ridge and XGBoostRegressor
compute RMSE, MAE, R^2
select model with highest R^2
persist artifact and metadata
```

Matchup predictor training pseudocode:

```text
df = get_match_differential_features_bulk(db)
if rows < 50: stop
drop rows without team100_won label
sort by match_id
median-impute features
split 80/20
train logistic + xgboost classifier
select by ROC-AUC
save artifact with feature importances
```

### 13.17 End-to-End Inference Pseudocode

Per-player win inference pseudocode:

```text
artifact = load win_predictor
if artifact missing: return model_trained false
match_time = query matches[match_id].game_creation
rolling = get_rolling_features(puuid, before=match_time)
if games_in_window < 5: return low confidence, no probability
row = build feature row from rolling
row = fill missing from artifact train medians
if scaler exists: transform row
proba = model.predict_proba(row)[win_class]
return probability + confidence tier + metadata
```

Early-game inference pseudocode:

```text
artifact = load earlygame_predictor
timeline_features = get_timeline_features(match_id)
if no timeline row: return no_timeline_data
fill missing with train medians
scale
proba_team100 = logistic.predict_proba
return team100 and team200 probabilities
```

### 13.18 Worked Numeric Examples

Example A: derived metrics for one participant.

Given:

- kills = 8, deaths = 2, assists = 6
- total_minions_killed = 180, neutral_minions_killed = 24
- gold_earned = 14200
- vision_score = 31
- game_duration_seconds = 1920 (32 minutes)
- team_kills = 26
- player_damage_to_champions = 24000
- team_damage_to_champions = 96000

Computation:

- KDA = (8 + 6) / max(2, 1) = 7.0
- CS = 180 + 24 = 204
- CS_per_min = 204 / 32 = 6.375
- Gold_per_min = 14200 / 32 = 443.75
- Vision_per_min = 31 / 32 = 0.969
- Kill_participation = (8 + 6) / 26 = 0.538
- Damage_share = 24000 / 96000 = 0.25

Example B: threat score with default weights.

Given:

- win_rate = 0.61
- kda = 4.2
- games = 18
- wr_weight = 4.0
- kda_weight = 4.0

Computation:

- wr_component = min(0.61, 1.0) * 4.0 = 2.44
- kda_component = min(4.2 / 8.0, 1.0) * 4.0 = 2.10
- confidence = min(18 / 20, 1.0) * 2.0 = 1.80
- threat_score = 2.44 + 2.10 + 1.80 = 6.34

Example C: role-card composite in teams/matchup.

If blue has:

- win_rate = 0.57
- role-normalized KDA signal converted to 0.62
- cs_norm = 0.71

Then blue composite is:

- 0.57 * 0.45 + 0.62 * 0.35 + 0.71 * 0.20
- 0.2565 + 0.2170 + 0.1420
- 0.6155

Compare against red composite to decide edge label.

### 13.19 Practical Interpretation Notes

How to read model confidence and outputs:

- low confidence on per-player predictions usually means fewer than 5 prior games
- matchup model quality strongly depends on having tracked opponents, not only tracked primary players
- early-game probability is only as good as timeline coverage quality
- recommendation quality improves after backfills because feature completeness rises

What improves model quality fastest:

1. increase tracked player diversity, not just match count for one player
2. keep derived metrics and timeline coverage high via backfill routes
3. retrain models after large ingestion batches
