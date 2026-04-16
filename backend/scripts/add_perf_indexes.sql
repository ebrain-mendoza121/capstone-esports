-- Performance indexes to resolve 504 timeouts under concurrent load.
--
-- Run this ONCE in the Supabase SQL editor (or via psql).
-- All statements use CREATE INDEX CONCURRENTLY IF NOT EXISTS so they are
-- safe to run on a live database without locking writes.
--
-- After running, verify with:
--   SELECT indexname, indexdef FROM pg_indexes WHERE tablename IN
--   ('participant_stats','derived_metrics','team_bans');

-- ── participant_stats ──────────────────────────────────────────────────────
-- Covering index: satisfies GROUP BY player_id + COUNT(match_id) as a pure
-- index scan (no heap access).  Also used by JOIN ON player_id=X AND match_id=Y
-- in the metrics and trends queries.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_participant_stats_player_match
    ON participant_stats (player_id, match_id);

-- Composite for role-performance per-player breakdown
-- (WHERE player_id = X AND role IN ('TOP','JUNGLE',...))
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_participant_stats_player_role
    ON participant_stats (player_id, role);

-- ── derived_metrics ────────────────────────────────────────────────────────
-- The existing unique constraint uq_derived_metrics_match_puuid is on
-- (match_id, puuid) — leading with match_id.  Add a (puuid, match_id) index
-- so queries that filter first by puuid can use an index scan from the left.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_derived_metrics_puuid_match
    ON derived_metrics (puuid, match_id);

-- ── team_bans ──────────────────────────────────────────────────────────────
-- champion ban-rate queries filter by champion_id; a composite with match_id
-- lets the planner avoid a heap fetch for the count.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_team_bans_champion_match
    ON team_bans (champion_id, match_id);
