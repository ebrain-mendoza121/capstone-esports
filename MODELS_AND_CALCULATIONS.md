# Models and Calculations Summary

## Overview
This document explains all database models and derived metric calculations in the League of Legends analytics platform. The system ingests match data from Riot API, stores raw statistics, and computes performance metrics.

---

## Database Models

### 1. Player Model (`players`)
Stores Riot account information for tracked players.

**Fields:**
- `id` (PK) - Auto-increment primary key
- `riot_id` - Riot ID game name (e.g., "Doublelift")
- `tag_line` - Riot ID tag line (e.g., "NA1")
- `puuid` - Universal unique player identifier (indexed, unique)
- `region` - Regional routing value: americas, europe, asia, sea
- `created_at` - Timestamp of first ingestion

**Key Points:**
- PUUID is the primary identifier across Riot services
- Region stores routing value (not platform code)
- Upserted on every ingestion to keep data fresh

---

### 2. Match Model (`matches`)
Stores match metadata for each game.

**Fields:**
- `match_id` (PK) - Riot match ID (e.g., "NA1_1234567890")
- `game_creation` - Unix timestamp in milliseconds (indexed)
- `game_duration` - Duration in seconds (normalized)
- `queue_id` - Queue type identifier (indexed)
  - 420 = Ranked Solo/Duo
  - 440 = Ranked Flex
- `patch_version` - Game version (e.g., "13.24.1")
- `created_at` - Ingestion timestamp

**Duration Normalization:**
Riot API changed behavior in patch 11.20:
- Pre-11.20: `gameDuration` in milliseconds
- Post-11.20: `gameDuration` in seconds (when `gameEndTimestamp` exists)

The system detects this and normalizes all durations to seconds.

---

### 3. ParticipantStats Model (`participant_stats`)
Stores per-player performance in each match.

**Fields:**
- `id` (PK) - Auto-increment
- `match_id` (FK) - References matches table (indexed)
- `player_id` (FK) - References players table (indexed)
- `team_id` - Team identifier (100 or 200)
- `champion` - Champion name (indexed)
- `role` - Lane position (TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY)
- `kills` - Champion kills
- `deaths` - Deaths
- `assists` - Kill assists
- `gold_earned` - Total gold earned
- `total_damage` - Damage dealt to champions
- `cs` - Creep score (minions + jungle monsters)
- `vision_score` - Vision control metric
- `win` - Boolean win flag

**CS Calculation:**
```python
cs = totalMinionsKilled + neutralMinionsKilled
```

---

### 4. TeamObjectives Model (`team_objectives`)
Stores team-level objective counts per match.

**Fields:**
- `id` (PK) - Auto-increment
- `match_id` (FK) - References matches table (indexed)
- `team_id` - Team identifier (100 or 200)
- `towers` - Tower kills
- `dragons` - Dragon kills
- `barons` - Baron Nashor kills
- `win_flag` - Boolean win flag

**Note:** Two records per match (one per team).

---

### 5. TeamBans Model (`team_bans`)
Stores champion bans from draft phase.

**Fields:**
- `id` (PK) - Auto-increment
- `match_id` (FK) - References matches table (indexed)
- `team_id` - Team identifier (100 or 200)
- `champion_id` - Banned champion ID (indexed)
- `pick_turn` - Ban order (1-5 per team)

**Key Points:**
- Only exists for draft modes (Ranked, Draft Pick)
- championId = -1 means no ban (filtered out)
- Composite index on (match_id, team_id) for efficient queries

---

### 6. DerivedMetrics Model (`derived_metrics`)
Stores pre-calculated performance metrics per player per match.

**Fields:**
- `id` (PK) - Auto-increment
- `match_id` (FK) - References matches table (indexed)
- `puuid` (FK) - References players table (indexed)
- `kda` - Kill/Death/Assist ratio
- `cs_per_min` - Creep score per minute
- `gold_per_min` - Gold per minute
- `kill_participation` - Team kill participation (0.0-1.0)
- `damage_share` - Team damage share (0.0-1.0)
- `vision_per_min` - Vision score per minute

**Constraints:**
- Unique constraint on (match_id, puuid)
- Upserted during ingestion (handles re-ingestion)

---

## Derived Metrics Calculations

All metrics are computed in `derived_metrics_calculator.py` using pure functions.

### 1. KDA (Kill/Death/Assist Ratio)
```python
kda = (kills + assists) / max(deaths, 1)
```
**Edge Case:** If deaths = 0, use 1 as denominator (standard convention).

**Example:**
- 10 kills, 2 deaths, 8 assists → KDA = 18/2 = 9.0
- 5 kills, 0 deaths, 3 assists → KDA = 8/1 = 8.0

---

### 2. CS Per Minute
```python
cs_per_min = cs / game_minutes
```
**Calculation:**
- CS = totalMinionsKilled + neutralMinionsKilled
- game_minutes = game_duration_seconds / 60

**Example:**
- 180 CS in 30-minute game → 180/30 = 6.0 CS/min

---

### 3. Gold Per Minute
```python
gold_per_min = gold_earned / game_minutes
```
**Example:**
- 12,000 gold in 30-minute game → 12000/30 = 400 gold/min

---

### 4. Kill Participation
```python
kill_participation = (kills + assists) / team_kills
```
**Range:** 0.0 to 1.0 (stored as decimal, not percentage)

**Edge Case:** If team_kills = 0, participation = 0.0

**Example:**
- Player: 5 kills, 10 assists
- Team: 30 total kills
- Participation = 15/30 = 0.50 (50%)

---

### 5. Damage Share
```python
damage_share = player_damage / team_damage
```
**Range:** 0.0 to 1.0 (stored as decimal, not percentage)

**Edge Case:** If team_damage = 0, share = 0.0

**Example:**
- Player: 25,000 damage
- Team: 100,000 total damage
- Share = 25000/100000 = 0.25 (25%)

---

### 6. Vision Per Minute
```python
vision_per_min = vision_score / game_minutes
```
**Example:**
- 45 vision score in 30-minute game → 45/30 = 1.5 vision/min

---

## Ingestion Flow

### Step-by-Step Process

1. **Player Lookup**
   - Call Riot Account-V1 API with gameName + tagLine
   - Get PUUID
   - Upsert player record

2. **Match ID Retrieval**
   - Call Match-V5 API with PUUID + filters (queue, count)
   - Get list of match IDs
   - Filter by queue type (default: 420 = Ranked Solo)

3. **Match Processing** (for each match ID)
   - Check if match already exists (skip if yes)
   - Fetch full match details from Match-V5 API
   - Normalize game duration (handle patch 11.20 change)
   - Insert match record
   - Insert participant stats for tracked player
   - Insert team objectives (2 records per match)
   - Insert team bans (if draft mode)
   - Compute and upsert derived metrics

4. **Transaction Management**
   - Each match processed independently
   - Failed matches don't poison entire batch
   - Single commit at end for all successful inserts

---

## Platform and Routing

### Platform Codes
Valid platform values (case-insensitive):
- NA, BR, LAN, LAS (Americas)
- KR, JP (Asia)
- EUNE, EUW, ME1, TR, RU (Europe)
- OCE, SG2, TW2, VN2 (SEA)

### Routing Mapping
```python
PLATFORM_TO_ROUTING = {
    NA/BR/LAN/LAS → "americas"
    KR/JP → "asia"
    EUNE/EUW/ME1/TR/RU → "europe"
    OCE/SG2/TW2/VN2 → "sea"
}
```

**Usage:**
- Account-V1 API uses routing
- Match-V5 API uses routing
- Platform stored in request, routing stored in database

---

## Edge Cases and Error Handling

### 1. Game Duration Normalization
**Problem:** Riot API changed duration format in patch 11.20

**Solution:**
```python
if gameEndTimestamp exists:
    duration_seconds = gameDuration  # Already in seconds
else:
    duration_seconds = gameDuration / 1000  # Convert from ms
```

### 2. Zero Deaths KDA
**Problem:** Division by zero when player has no deaths

**Solution:** Use max(deaths, 1) as denominator
```python
kda = (kills + assists) / max(deaths, 1)
```

### 3. Zero Team Stats
**Problem:** Division by zero for kill participation / damage share

**Solution:** Return 0.0 if team total is zero
```python
kill_participation = (kills + assists) / team_kills if team_kills > 0 else 0.0
```

### 4. Missing Bans
**Problem:** Non-draft modes have championId = -1

**Solution:** Filter out bans where championId == -1
```python
if champion_id and champion_id != -1:
    insert_ban()
```

### 5. Match Re-ingestion
**Problem:** Same match ingested multiple times

**Solution:** 
- Check match_exists() before fetching details
- Upsert derived_metrics with unique constraint

---

## Aggregate Metrics (On-Demand)

The `MetricsService` computes aggregate statistics across all matches for a player:

### Calculated Metrics
- **Matches Played** - Total match count
- **Win Rate** - wins / total_matches
- **Average KDA** - (total_kills + total_assists) / total_deaths
- **Average CS/min** - total_cs / total_minutes
- **Average Gold/min** - total_gold / total_minutes
- **Average Vision/min** - total_vision / total_minutes

**Note:** These are computed on-demand from participant_stats, not from derived_metrics table.

---

## Future Enhancements

### Potential Additions
1. **Timeline Data** - Minute-by-minute events (gold diff, XP diff)
2. **Item Builds** - Final item sets per match
3. **Runes/Summoners** - Rune choices and summoner spells
4. **Champion Mastery** - Per-champion aggregate stats
5. **Role Performance** - Stats broken down by lane position
6. **Patch Analysis** - Performance trends across patches
7. **Matchup Analysis** - Champion vs champion statistics

---

## Summary

The system provides a complete pipeline from Riot API ingestion to derived metrics:

1. **Raw Data** - Stored in matches, participant_stats, team_objectives, team_bans
2. **Derived Metrics** - Pre-calculated per-match performance metrics
3. **Aggregate Stats** - On-demand calculations across match history

All calculations handle edge cases (zero deaths, zero team stats, duration normalization) and use standard League of Legends conventions (KDA with deaths=1, participation as decimal).
