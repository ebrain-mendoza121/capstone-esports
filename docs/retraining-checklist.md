# ML Model Retraining Checklist

Trigger this checklist any time **any** of the following happen:
- `requirements.txt` ML pin changes (`scikit-learn`, `xgboost`, `pandas`, `numpy`, `joblib`)
- New match data is bulk-ingested (≥ 500 new matches recommended)
- `feature_extractor.py` changes any query, column name, or derived feature
- `CLUSTERING_FEATURES`, `ROLLING_FEATURES`, or `TIMELINE_FEATURES` lists change

---

## Pre-flight

- [ ] Confirm the server is running the **pinned** library versions:
  ```bash
  source backend/.venv/bin/activate
  python -c "import sklearn, xgboost; print(sklearn.__version__, xgboost.__version__)"
  # must match requirements.txt: scikit-learn==1.8.0  xgboost==3.2.0
  ```
- [ ] Ensure `GET /health` returns `200` and the DB has live data.
- [ ] Confirm ranked-solo data exists:
  ```sql
  SELECT COUNT(*) FROM matches WHERE queue_id = 420;
  SELECT COUNT(*) FROM derived_metrics;
  ```
  Minimums: **20 players × 10 matches** for playstyle; **100 participant rows** for win-prediction.

---

## Step 1 — Back up current artifacts

```bash
cp backend/ml_models/playstyle_kmeans.joblib \
   backend/ml_models/playstyle_kmeans.$(date +%Y%m%d).bak.joblib

cp backend/ml_models/win_predictor.joblib \
   backend/ml_models/win_predictor.$(date +%Y%m%d).bak.joblib
```

---

## Step 2 — Retrain playstyle model

```bash
curl -s -X POST http://localhost:8000/ai/train/playstyle | python -m json.tool
```

Expected response fields: `status: "trained"`, `silhouette_score`, `inertia`, `centroids`.

**After this step** — review the logged centroid values and update
`CLUSTER_LABELS` in `backend/app/services/ai_service.py` if cluster
characteristics have shifted:

```python
# ai_service.py
CLUSTER_LABELS: dict[int, str] = {
    0: "carry",      # ← review these after each retrain
    1: "support",
    2: "farming",
    3: "aggressive",
}
```

A good silhouette score is ≥ 0.25.  Below 0.15 indicates clusters are
not meaningful — consider increasing data volume before exposing to users.

---

## Step 3 — Retrain win-prediction model

```bash
curl -s -X POST http://localhost:8000/ai/train/win-prediction | python -m json.tool
```

Expected response fields: `status: "trained"`, `model_type`, `accuracy`, `roc_auc`, `top_factors`.

Acceptable thresholds:
- `roc_auc` ≥ 0.60 (random baseline = 0.50)
- `accuracy` ≥ 0.55

If XGBoost degrades below Logistic Regression, the training set is likely
too sparse — ingest more players before retraining.

---

## Step 4 — Verify new artifacts have version metadata

```python
import joblib, pathlib
for name in ("playstyle_kmeans", "win_predictor"):
    a = joblib.load(pathlib.Path(f"backend/ml_models/{name}.joblib"))
    print(name, a["sklearn_version"], a["xgboost_version"], a["trained_at"])
```

Both files must have `sklearn_version == "1.8.0"` and `xgboost_version == "3.2.0"`.

---

## Step 5 — Smoke-test inference

Replace `<puuid>` with any ingested player puuid.

```bash
# Playstyle
curl -s "http://localhost:8000/ai/playstyle/<puuid>" | python -m json.tool

# Win-prediction (needs a known match_id for that player)
curl -s "http://localhost:8000/ai/predict/<puuid>/<match_id>" | python -m json.tool

# Champion recommendations
curl -s "http://localhost:8000/ai/champions/<puuid>?top_n=5" | python -m json.tool

# Model status (confirm trained_at timestamps updated)
curl -s "http://localhost:8000/ai/models/status" | python -m json.tool
```

Verify:
- `playstyle_label` is not `"insufficient_data"` for a player with 10+ games
- `win_probability` is a float in `[0, 1]`
- `model_status` shows both models as `trained: true` with today's `trained_at`

---

## Step 6 — Invalidate in-process cache (running server)

The in-process `_model_cache` is evicted automatically at retrain time
(via `invalidate_model_cache()`).  If a retrain was done against a
**different** running process (e.g., via direct script), restart the
server to pick up the new artifacts:

```bash
# Graceful restart (uvicorn with --reload active in dev)
touch backend/app/main.py

# Production restart
systemctl restart esports-api   # or however the service is managed
```

---

## Upgrade path (bumping an ML library version)

1. Update the pin in `requirements.txt`.
2. Run `pip install -r requirements.txt` in the venv.
3. Delete existing `.joblib` files (they are incompatible).
4. Run Steps 1–6 above.

Never deploy a version bump without completing a full retrain first.
