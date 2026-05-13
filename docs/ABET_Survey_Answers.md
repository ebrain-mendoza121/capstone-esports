# ABET Assessment Answers — CIIC/INSO 4151 Capstone
## Individual Survey Responses
**Student:** Ebrain Mendoza (ebmendoza / ebrain-mendoza121)
**Project:** Esports Analytics Platform — League of Legends Match Analytics System
**Course:** CIIC/INSO 4151 — Senior Capstone Design
**Date:** May 2026

---

# SECTION 1: Complex Problem Solving (C1-E1)

---

## Question 1: Describe how you can formulate a clear problem statement for a project.

A clear problem statement requires identifying three interconnected elements: **who** is affected, **what** specific difficulty they face, and **why** existing solutions are insufficient.

The process begins with stakeholder analysis — understanding the domain deeply enough to recognize that a problem is real and not imagined. In engineering terms, this means distinguishing a *symptom* (e.g., "coaches waste time on spreadsheets") from a *root cause* (e.g., "there is no automated system that normalizes per-minute performance metrics and ties them to predictive intelligence").

A well-formed problem statement should be:

- **Specific** — it names the affected population and the exact deficiency, not a vague dissatisfaction
- **Measurable** — it implies criteria that would indicate when the problem is solved (e.g., "coaches can retrieve a player's normalized KPI report in under 2 seconds")
- **Bounded** — it excludes problems that are out of scope to keep the solution feasible
- **Free of assumed solutions** — the problem statement should describe the gap, not prescribe a technology

Practically, the formulation process involves domain research, user interviews (or equivalent context gathering), and iterating draft statements until the team can unanimously confirm: *"If we built something that addressed this statement and nothing else, it would be genuinely useful."*

Constraints — time, budget, access to data, regulatory limits — are identified in parallel and incorporated as boundary conditions that the solution must respect, not as reasons to weaken the problem statement.

---

## Question 2: In the context of your capstone project, describe how you identified a proper solution approach.

The capstone project targets a real gap in the collegiate esports ecosystem: the absence of a unified, data-driven analytics tool that connects player match history to predictive and prescriptive intelligence.

**Problem identification process:**

1. **Domain analysis** — I examined what professional esports organizations use (Mobalytics, OP.GG, League of Graphs) and found that these tools either lack team-level composition analysis, do not expose ML-backed predictions, or do not allow teams to ingest their own roster's data in bulk.

2. **Constraint mapping** — The project had to be completed within a single academic semester, run on free-tier cloud infrastructure (Supabase, Railway, Vercel), and use a public API (Riot Games Developer API) that has real rate limits.

3. **Solution space exploration** — I evaluated several architectural approaches:
   - A purely frontend scraping tool (rejected — violates Riot ToS, brittle)
   - A static analysis dashboard with hardcoded data (rejected — no real ingestion, no ML)
   - A full-stack platform with a relational backend, async ingestion pipeline, and trainable ML models (selected — addresses the root cause, is extensible, and maps naturally to a capstone-scale codebase)

4. **Feasibility gate** — The selected approach required: a Python backend with ML libraries (available via pip), a managed database (Supabase free tier), and a Riot API key (obtainable via Riot Developer Portal). All three constraints were satisfied before committing to the architecture.

5. **Decomposition into SMART goals** — The abstract solution was converted into four verifiable SMART goals (≥95% derived metric coverage, <2,000 ms response time, ≥5 players ingested, ≥10,000-row capacity) and one stress test target (50 concurrent users with p95 <2 seconds and <1% failure rate). These provided measurable success criteria throughout development.

The result was an architecture that flows: **Riot API → FastAPI ingestion → PostgreSQL → ML training → REST endpoints → Next.js dashboard**. Each layer is independently testable, which was critical for a team-based project with CI/CD enforcement.

---

## Question 3: In the context of your capstone project, discuss the feasibility of the solution within the given constraints.

The solution was assessed across four categories of constraints:

### Technical Feasibility

The core technical challenge was building a working ML pipeline on top of a live sports data API within a semester. Each component had established precedent:

- FastAPI + SQLAlchemy is a well-documented production stack used widely in industry
- scikit-learn and XGBoost are mature libraries with extensive documentation and community support
- The Riot Games API is well-documented and has a free developer tier with sufficient rate limits for a prototype scale

Risks that were identified and mitigated:
- *Rate limiting* — handled with exponential backoff, retry logic (up to 6 retries), and slowapi middleware
- *Insufficient training data* — handled by implementing minimum data gates per model; models report "untrained" via `/ai/models/status` if sample sizes are below threshold
- *SQLAlchemy compatibility issue with PostgreSQL ARRAY types* — resolved by using explicit `cast(ARRAY[...], ARRAY[Integer()])` syntax (documented in repository memory)

### Economic Feasibility

The entire production deployment runs on free-tier services:
- Supabase free tier for PostgreSQL
- Railway free tier for backend hosting
- Vercel free tier for frontend hosting
- Riot Developer API free key

Total infrastructure cost: **$0/month** for the capstone scope, which is within the student project budget constraint.

### Schedule Feasibility

The project was delivered across approximately 10 weeks of active development (March 5 – May 11, 2026), with 89+ commits from the primary developer alone. The workload was distributed across six phases:

1. Bootstrap and schema design (Week 1)
2. Core ingestion and backend routes (Weeks 2–4)
3. ML pipeline and analytics (Week 5)
4. Team insights, testing, advanced features (Week 6)
5. Deployment and performance tuning (Week 7)
6. Final optimization, caching, and stress testing (Week 8)

The phased delivery allowed the team to demonstrate working software at each milestone rather than deferring integration to the end.

### Operational Feasibility

The final system met all SMART goals under verified conditions:
- **Derived metric coverage**: 100% across 36,100 rows (target: ≥95%)
- **API response time**: ≤922 ms on all tested endpoints (target: <2,000 ms)
- **Players ingested**: 14,205 players in the database (target: ≥5)
- **Match capacity**: 36,100 participant-match rows (target: ≥10,000)
- **Stress test**: 50 concurrent users sustained for 60 seconds with p95 <2,000 ms and <1% failure rate

The solution is feasible, proven, and deployed in production.

---

# SECTION 2: Design and Implementation (C2-E2)

---

## Question 1: In the context of your capstone project, describe how the design you proposed complies with the requirements and professional standards or best practices.

### Compliance with Requirements

Each functional requirement was mapped to a verifiable system component:

| Requirement | Implementation | Evidence |
|-------------|----------------|---------|
| Ingest player match data from Riot API | `POST /ingest/player`, `POST /ingest/players/batch` | Integration tests in `test_ingest_validation.py` |
| Compute normalized performance KPIs | `derived_metrics` table; `DerivedMetricsCalculator` service | 100% coverage measured by `GET /backfill/status` |
| Serve analytics to frontend | 20+ analytics endpoints under `/analytics`, `/metrics`, `/champions`, `/teams` | Smoke-tested via `test_api.sh`, benchmark verified |
| Train and serve ML models | 7 models under `/ai/train/*` and `/ai/*` | `GET /ai/models/status` reports trained state per artifact |
| Support team composition analysis | `POST /teams/build`, `POST /teams/matchup`, role matchup cards | Connected to frontend team-insights page |
| Sustain 50 concurrent users | TTL cache, composite DB indexes, statement timeouts | Locust stress test results in `stress_results_stats.csv` |

### Compliance with Professional Standards and Best Practices

**1. API Design (REST conventions)**
All endpoints follow REST conventions: resource-based URLs, correct HTTP verbs (GET for reads, POST for mutations), meaningful status codes (200, 404, 422, 500), and kebab-case URL segments. The API is fully self-documenting via OpenAPI/Swagger at `/docs`.

**2. Security (OWASP alignment)**
- No secrets are stored in source code — all sensitive values loaded via environment variables and `pydantic-settings`
- CORS is configured with an explicit allow-list, not a wildcard
- Rate limiting (slowapi) protects ingestion endpoints from abuse or accidental runaway loops
- Input validation is enforced at the API boundary via Pydantic schemas before any DB write
- Exception handlers ensure error responses never leak internal stack traces to clients while maintaining CORS headers

**3. Data Integrity**
- Prisma-managed migrations provide a versioned, auditable schema history
- Foreign key constraints with `ON DELETE CASCADE` maintain referential integrity across all related tables
- Unique constraints (e.g., `uq_derived_metrics_match_puuid`) prevent duplicate derived metric rows

**4. ML Model Governance**
- All trained models are persisted with metadata sidecars recording: `trained_at`, `sample_count`, `metrics` (AUC, R², RMSE), `sklearn_version`, `xgboost_version`
- Temporal train/test split prevents data leakage — future match outcomes cannot influence historical training rows
- Training medians are persisted alongside each model to ensure inference-time imputation is consistent with training

**5. Code Quality**
- `flake8` linting enforced in CI on every push and pull request
- Conventional commit message format maintained throughout the commit history
- Services are organized by responsibility (ingestion, metrics, feature extraction, AI) with clear module boundaries

**6. Testing**
- Three test layers: unit (pure function logic), integration (endpoint behavior against a test DB), and stress (load profile with Locust)
- Coverage threshold enforced in CI to prevent untested code from merging

---

## Question 2: Describe the tools and methodologies you use in the capstone project and justify why you selected those tools and methodologies.

### Backend Framework — FastAPI

**Justification:** FastAPI was selected over Flask and Django REST Framework because it is async-native (critical for concurrent Riot API calls during ingestion), generates OpenAPI documentation automatically (saving documentation overhead), and uses Python type hints for input validation through Pydantic. For a project where self-documentation was important for team collaboration and academic review, the auto-generated Swagger UI at `/docs` was a practical advantage.

### Database — PostgreSQL on Supabase

**Justification:** A relational model was required because the data has well-defined relationships (players → matches → participant_stats → derived_metrics). PostgreSQL supports JSONB columns for flexible timeline frame storage without requiring a separate document store. Supabase provides managed PostgreSQL with a free tier, eliminating the need for local database infrastructure or paid hosting during development.

### ORM and Migrations — SQLAlchemy + Prisma

**Justification:** SQLAlchemy was used for runtime queries because it is the dominant Python ORM, supports async sessions, and integrates seamlessly with FastAPI's dependency injection system. Prisma was used for schema management because its declarative `schema.prisma` file and named migrations provide an auditable change history that is easier to review in pull requests than raw SQL files.

### ML Libraries — scikit-learn + XGBoost

**Justification:** scikit-learn provides the full ML toolkit (KMeans, Logistic Regression, Ridge, StandardScaler, train/test split, evaluation metrics) in a unified, well-tested API. XGBoost was added as a candidate model for classification and regression tasks because gradient-boosted trees consistently outperform linear models on tabular sports data with non-linear feature interactions. The project uses a **candidate model selection pattern** — both a linear baseline and an XGBoost model are trained, and the better performer by AUC or R² is persisted.

### Feature Engineering — pandas

**Justification:** pandas DataFrames provide the most natural representation for time-ordered match history windows. Operations like rolling means, standard deviation, and least-squares trend slopes (CS trend) map directly to pandas built-in methods, reducing custom logic and potential bugs.

### Load Testing — Locust

**Justification:** Locust is Python-native (no Java/Scala dependency like Gatling or JMeter), scriptable in pure Python with a clean class-based user model, and generates structured CSV and HTML reports automatically. The task-weight model mirrors real dashboard usage patterns (per-player endpoints weighted 4–5×, global analytics 1–2×), making the test more representative than simple uniform polling.

### Deployment — Railway + Vercel

**Justification:** Both platforms support zero-configuration deployment from a GitHub repository. Railway auto-detects Python applications and reads the `Procfile` for the start command. Vercel auto-detects Next.js projects. This eliminated DevOps overhead (no Dockerfiles, no Kubernetes, no nginx config) while still providing production-grade hosting with TLS, auto-scaling, and environment variable management.

### CI/CD — GitHub Actions

**Justification:** GitHub Actions is free for public repositories, integrates directly with pull requests, and requires no external CI server. The workflow runs `pytest` (with coverage) and `flake8` on every push. This enforced code quality standards without manual review overhead and caught integration regressions introduced by concurrent team members.

### Methodology — Phased Iterative Development

**Justification:** The project followed an iterative, phase-based delivery model rather than a waterfall approach. Each phase delivered working, testable software: Phase 1 produced a running API; Phase 2 produced ingestion; Phase 3 produced ML training; Phase 4 produced team analytics; Phase 5 produced a deployed production system; Phase 6 produced a performance-hardened system with verified stress test results. This approach reduced integration risk, allowed early validation of SMART goals, and made progress visible to the team and advisor at each milestone.

---

## Question 3: In the context of your capstone project, describe how you showed the solution complies with the requirements.

The compliance demonstration used five interlocking verification mechanisms:

### 1. Automated Unit Tests (`pytest`)

Unit tests in `backend/tests/unit/` verify the correctness of individual computation functions in isolation:

- `test_derived_metrics.py` — asserts that KDA, CS/min, gold/min, kill participation, damage share, and vision/min are computed correctly for known input values, including edge cases (zero deaths, zero game duration, zero team kills)
- `test_feature_helpers.py` — validates rolling window computations, win streak calculation, and KDA standard deviation
- `test_metrics_aggregation.py` — verifies that player-level aggregate metrics (average KDA, average CS/min, etc.) are computed correctly from a set of known participant rows

These tests run automatically in GitHub Actions CI on every push and pull request, providing continuous assurance that core computation logic has not regressed.

### 2. Automated Integration Tests (`pytest` + TestClient)

Integration tests in `backend/tests/integration/` verify that HTTP endpoints behave correctly end-to-end:

- `test_health.py` confirms the API is reachable and the database connection is healthy
- `test_ingest_validation.py` verifies that malformed ingestion requests return appropriate 422 validation errors
- `test_analytics_routes.py` confirms that analytics endpoints return 200 with structurally valid JSON
- `test_ai_endpoints.py` verifies that ML training endpoints respond correctly and that inference endpoints return expected response shapes

### 3. API Smoke Test Script (`test_api.sh`)

`test_api.sh` is a curl-based script that exercises all major endpoint categories against a running backend and prints pass/fail for each. This provides a human-readable acceptance test that can be run against any environment (local, staging, production).

### 4. Benchmark Script (`benchmark.sh`) — SMART Goal Verification

`benchmark.sh` directly verifies the four quantitative SMART goals by querying the live backend and comparing measured values to thresholds:

| SMART Goal | How Measured | Verified Value | Pass |
|------------|-------------|----------------|------|
| Derived metric coverage ≥95% | `GET /backfill/status` → `coverage_percentage` | 100.0% | ✅ |
| API response time <2,000 ms | `curl -w "%{time_total}"` on 6 endpoints | Max 922 ms | ✅ |
| Players ingested ≥5 | `GET /players/` → count | 14,205 | ✅ |
| Match rows ≥10,000 | `GET /backfill/status` → `total_matches` | 36,100 | ✅ |

Results are persisted to `performance_evidence.md` for reproducible audit.

### 5. Stress Test (Locust) — Concurrency Requirement

The Locust stress test in `backend/tests/stress/locustfile.py` simulates 50 concurrent users for 60 seconds with a 5-user/second spawn rate. The test exercises a realistic mix of endpoints weighted by expected real-world usage frequency. Results are exported to CSV and HTML:

| Metric | Required | Result |
|--------|----------|--------|
| Concurrent users sustained | 50 | ✅ Achieved |
| p95 response time | <2,000 ms | ✅ Achieved |
| Failure rate | <1% | ✅ Achieved |
| Throughput | >10 req/s | ✅ Achieved |

The stress test was introduced after adding the TTL cache with stampede protection and composite DB indexes (`commit 9b810a1`). Before those optimizations, the system showed elevated failure rates under concurrent load, providing a direct before/after comparison demonstrating that the implementation changes resolved the compliance gap.

### 6. ML Model Status Endpoint

`GET /ai/models/status` provides runtime proof that each ML artifact has been successfully trained, returning for each model: `trained_at`, `sample_count`, `metrics` (AUC, R², RMSE/MAE), `model_type`, and `sklearn_version` / `xgboost_version`. This endpoint was used during the project demonstration to confirm that all 7 models were trained and deployable.

---

*This document was prepared in accordance with ABET student outcome assessment requirements for CIIC/INSO 4151 at the University of Puerto Rico.*
