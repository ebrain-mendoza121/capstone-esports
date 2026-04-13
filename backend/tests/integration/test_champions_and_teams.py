"""
Integration tests for Phase 1 (Champions Module) and Phase 2 (Team Builder
Champion + Role Expansion).

Strategy
--------
DDragon fetches go over the network, so every test that calls a champion
endpoint patches ``app.api.routes.champions._full_map`` (or the ddragon
getters directly) with a small in-memory fixture.  This keeps tests fast
and hermetic.

Riot API calls inside ``get_team_stats`` / ``get_live_player_stats`` are
patched to return empty/minimal stats so the teams endpoints can be
exercised without a live Riot key.

PostgreSQL-specific SQL (``::`` casts, ``ANY(:param)``) used in the DB
stats helpers causes SQLite test failures; those code paths are xfail-marked.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# DDragon fixture data — two real-looking champions used across all tests
# ---------------------------------------------------------------------------

_ANNIE: dict = {
    "id":             1,
    "key":            "Annie",
    "name":           "Annie",
    "title":          "the Dark Child",
    "tags":           ["Mage", "Support"],
    "image_url":      "https://ddragon.example.com/Annie.png",
    "image_filename": "Annie.png",
    "role_affinity":  ["MIDDLE", "UTILITY"],
    "blurb":          "A child mage.",
    "stats":          {"hp": 524},
}

_DARIUS: dict = {
    "id":             122,
    "key":            "Darius",
    "name":           "Darius",
    "title":          "the Hand of Noxus",
    "tags":           ["Fighter", "Tank"],
    "image_url":      "https://ddragon.example.com/Darius.png",
    "image_filename": "Darius.png",
    "role_affinity":  ["TOP", "JUNGLE"],
    "blurb":          "A powerful bruiser.",
    "stats":          {"hp": 582},
}

_JINX: dict = {
    "id":             222,
    "key":            "Jinx",
    "name":           "Jinx",
    "title":          "the Loose Cannon",
    "tags":           ["Marksman"],
    "image_url":      "https://ddragon.example.com/Jinx.png",
    "image_filename": "Jinx.png",
    "role_affinity":  ["BOTTOM"],
    "blurb":          "A chaotic marksman.",
    "stats":          {"hp": 610},
}

_THRESH: dict = {
    "id":             412,
    "key":            "Thresh",
    "name":           "Thresh",
    "title":          "the Chain Warden",
    "tags":           ["Support", "Tank"],
    "image_url":      "https://ddragon.example.com/Thresh.png",
    "image_filename": "Thresh.png",
    "role_affinity":  ["UTILITY", "JUNGLE"],
    "blurb":          "A deadly support.",
    "stats":          {"hp": 561},
}

_LEE_SIN: dict = {
    "id":             64,
    "key":            "LeeSin",
    "name":           "Lee Sin",
    "title":          "the Blind Monk",
    "tags":           ["Fighter", "Assassin"],
    "image_url":      "https://ddragon.example.com/LeeSin.png",
    "image_filename": "LeeSin.png",
    "role_affinity":  ["JUNGLE", "TOP"],
    "blurb":          "A mobile fighter.",
    "stats":          {"hp": 570},
}

_FULL_MAP: dict[int, dict] = {
    1:   _ANNIE,
    122: _DARIUS,
    222: _JINX,
    412: _THRESH,
    64:  _LEE_SIN,
}

# Reusable mock for get_champion_full_map (async)
_mock_full_map = AsyncMock(return_value=_FULL_MAP)

# Minimal player stats block returned by get_team_stats mock
def _fake_player_stat(name: str, role: str = "MIDDLE") -> dict:
    return {
        "summoner_name":       name,
        "puuid":               f"puuid-{name.lower()}",
        "source":              "db",
        "primary_role":        role,
        "win_rate_20":         0.55,
        "avg_kda_20":          3.1,
        "avg_cs_per_min_20":   7.2,
        "avg_gold_per_min_20": 380.0,
        "avg_kill_part_20":    0.62,
        "avg_vision_per_min_20": 1.2,
        "games_in_window":     20,
    }


# Marker for tests that need real PostgreSQL syntax
_PG_ONLY = pytest.mark.xfail(
    strict=False,
    reason=(
        "Requires PostgreSQL: raw SQL uses :: cast / window functions "
        "unsupported by the SQLite test database. Passes against real DB."
    ),
)


# ===========================================================================
# Phase 1 — Champions Module
# ===========================================================================


class TestChampionsList:
    """GET /champions — list with optional filters."""

    @pytest.mark.integration
    def test_returns_200_with_champion_list(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions")
        assert resp.status_code == 200
        data = resp.json()
        assert "champions" in data
        assert "count" in data
        assert isinstance(data["champions"], list)
        assert data["count"] == len(data["champions"])

    @pytest.mark.integration
    def test_champions_list_sorted_alphabetically(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions")
        names = [c["name"] for c in resp.json()["champions"]]
        assert names == sorted(names)

    @pytest.mark.integration
    def test_each_entry_has_required_fields(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions")
        for champ in resp.json()["champions"]:
            for field in ("id", "name", "title", "tags", "image_url", "role_affinity"):
                assert field in champ, f"Missing field '{field}' in champion entry"

    @pytest.mark.integration
    def test_role_filter_returns_only_matching_champions(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions?role=BOTTOM")
        assert resp.status_code == 200
        data = resp.json()
        # Jinx is the only BOTTOM champion in the fixture
        assert data["count"] == 1
        assert data["champions"][0]["name"] == "Jinx"

    @pytest.mark.integration
    def test_tag_filter_returns_only_matching_champions(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions?tag=Marksman")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["champions"][0]["name"] == "Jinx"

    @pytest.mark.integration
    def test_search_filter_case_insensitive(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions?search=ann")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["champions"][0]["name"] == "Annie"

    @pytest.mark.integration
    def test_invalid_role_returns_422(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions?role=CARRY")
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_ddragon_unavailable_returns_503(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            AsyncMock(return_value={}),
        ):
            resp = client.get("/champions")
        assert resp.status_code == 503


class TestChampionsByRole:
    """GET /champions/by-role/{role}."""

    @pytest.mark.integration
    def test_returns_champions_for_top(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions/by-role/TOP")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "TOP"
        assert "count" in data
        names = [c["name"] for c in data["champions"]]
        assert "Darius" in names
        assert "Lee Sin" in names
        assert "Annie" not in names   # Annie has no TOP affinity

    @pytest.mark.integration
    def test_response_sorted_alphabetically(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions/by-role/JUNGLE")
        names = [c["name"] for c in resp.json()["champions"]]
        assert names == sorted(names)

    @pytest.mark.integration
    def test_invalid_role_returns_422(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions/by-role/ADC")
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_returns_count_matching_list_length(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions/by-role/MIDDLE")
        data = resp.json()
        assert data["count"] == len(data["champions"])


class TestChampionDetail:
    """GET /champions/{champion_id}."""

    @_PG_ONLY
    @pytest.mark.integration
    def test_returns_champion_metadata(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions/1")   # Annie
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        assert data["name"] == "Annie"
        assert "tags" in data
        assert "role_affinity" in data
        assert "db_stats" in data

    @pytest.mark.integration
    def test_unknown_champion_returns_404(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions/99999")
        assert resp.status_code == 404


class TestChampionMatchup:
    """GET /champions/matchup/{champ_a_id}/{champ_b_id}."""

    @pytest.mark.integration
    def test_unknown_champion_a_returns_404(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions/matchup/99999/1")
        assert resp.status_code == 404

    @pytest.mark.integration
    def test_unknown_champion_b_returns_404(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions/matchup/1/99999")
        assert resp.status_code == 404

    @pytest.mark.integration
    def test_invalid_role_param_returns_422(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions/matchup/1/122?role=CARRY")
        assert resp.status_code == 422

    @_PG_ONLY
    @pytest.mark.integration
    def test_valid_matchup_returns_correct_shape(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions/matchup/1/122")
        assert resp.status_code == 200
        data = resp.json()
        assert "champ_a" in data
        assert "champ_b" in data
        assert "games_played" in data
        assert "confidence" in data
        assert data["champ_a"]["id"] == 1
        assert data["champ_b"]["id"] == 122

    @_PG_ONLY
    @pytest.mark.integration
    def test_matchup_with_role_scope(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions/matchup/1/122?role=MIDDLE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role_scope"] == "MIDDLE"

    @_PG_ONLY
    @pytest.mark.integration
    def test_empty_db_matchup_returns_zero_games(self, client):
        with patch(
            "app.api.routes.champions.get_champion_full_map",
            _mock_full_map,
        ):
            resp = client.get("/champions/matchup/1/122")
        assert resp.status_code == 200
        data = resp.json()
        assert data["games_played"] == 0
        assert data["champ_a_win_rate"] is None
        assert data["confidence"] == "low"


# ===========================================================================
# Phase 2 — Team Builder Champion + Role Expansion
# ===========================================================================

# Minimal get_team_stats mock — returns one player stat block per player input
def _make_team_stats_mock(roles: list[str]):
    names = ["Player1", "Player2", "Player3", "Player4", "Player5"][:len(roles)]
    return AsyncMock(return_value=[
        _fake_player_stat(name, role)
        for name, role in zip(names, roles)
    ])


class TestTeamsBuildChampionEnrichment:
    """POST /teams/build — champion_id / champion fields + composition_focus."""

    @pytest.mark.integration
    def test_build_without_champion_data_succeeds(self, client):
        """Baseline: build still works when no champion info is provided."""
        mock_stats = _make_team_stats_mock(["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"])
        with (
            patch("app.api.routes.teams.get_team_stats", mock_stats),
            patch("app.api.routes.teams.get_champion_full_map", _mock_full_map),
        ):
            resp = client.post("/teams/build", json={
                "players": [
                    {"game_name": "P1", "tag_line": "NA1", "role": "TOP"},
                    {"game_name": "P2", "tag_line": "NA1", "role": "JUNGLE"},
                    {"game_name": "P3", "tag_line": "NA1", "role": "MIDDLE"},
                    {"game_name": "P4", "tag_line": "NA1", "role": "BOTTOM"},
                    {"game_name": "P5", "tag_line": "NA1", "role": "UTILITY"},
                ],
                "platform": "NA",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "players" in data
        assert "composition_archetype" in data
        assert "synergy_flags" in data

    @pytest.mark.integration
    def test_build_with_champion_id_enriches_champion_meta(self, client):
        """When champion_id is provided, champion_meta must be populated."""
        mock_stats = _make_team_stats_mock(["MIDDLE"])
        with (
            patch("app.api.routes.teams.get_team_stats", mock_stats),
            patch("app.api.routes.teams.get_champion_full_map", _mock_full_map),
        ):
            resp = client.post("/teams/build", json={
                "players": [
                    {"game_name": "Faker", "tag_line": "T1", "role": "MIDDLE", "champion_id": 1},
                ],
                "platform": "KR",
            })
        assert resp.status_code == 200
        player = resp.json()["players"][0]
        assert player["champion_meta"] is not None
        assert player["champion_meta"]["name"] == "Annie"
        assert "tags" in player["champion_meta"]
        assert "image_url" in player["champion_meta"]
        assert "role_affinity" in player["champion_meta"]

    @pytest.mark.integration
    def test_build_with_champion_name_fallback(self, client):
        """When champion name is provided (no id), meta is still resolved."""
        mock_stats = _make_team_stats_mock(["TOP"])
        with (
            patch("app.api.routes.teams.get_team_stats", mock_stats),
            patch("app.api.routes.teams.get_champion_full_map", _mock_full_map),
        ):
            resp = client.post("/teams/build", json={
                "players": [
                    {"game_name": "P1", "tag_line": "NA1", "role": "TOP", "champion": "Darius"},
                ],
                "platform": "NA",
            })
        assert resp.status_code == 200
        player = resp.json()["players"][0]
        assert player["champion_meta"] is not None
        assert player["champion_meta"]["name"] == "Darius"

    @pytest.mark.integration
    def test_build_role_champion_fit_native(self, client):
        """Annie (Mage/Support → MIDDLE native) declared as MIDDLE = 'native'."""
        mock_stats = _make_team_stats_mock(["MIDDLE"])
        with (
            patch("app.api.routes.teams.get_team_stats", mock_stats),
            patch("app.api.routes.teams.get_champion_full_map", _mock_full_map),
        ):
            resp = client.post("/teams/build", json={
                "players": [
                    {"game_name": "P1", "tag_line": "NA1", "role": "MIDDLE", "champion_id": 1},
                ],
                "platform": "NA",
            })
        assert resp.status_code == 200
        fit = resp.json()["players"][0]["role_champion_fit"]
        assert fit == "native"

    @pytest.mark.integration
    def test_build_role_champion_fit_off_meta(self, client):
        """Jinx (Marksman → BOTTOM) declared as TOP = 'off-meta'."""
        mock_stats = _make_team_stats_mock(["TOP"])
        with (
            patch("app.api.routes.teams.get_team_stats", mock_stats),
            patch("app.api.routes.teams.get_champion_full_map", _mock_full_map),
        ):
            resp = client.post("/teams/build", json={
                "players": [
                    {"game_name": "P1", "tag_line": "NA1", "role": "TOP", "champion_id": 222},
                ],
                "platform": "NA",
            })
        assert resp.status_code == 200
        fit = resp.json()["players"][0]["role_champion_fit"]
        assert fit == "off-meta"

    @pytest.mark.integration
    def test_build_unknown_champion_id_gives_null_meta(self, client):
        """An unknown champion_id (not in DDragon) still returns 200 with null meta."""
        mock_stats = _make_team_stats_mock(["TOP"])
        with (
            patch("app.api.routes.teams.get_team_stats", mock_stats),
            patch("app.api.routes.teams.get_champion_full_map", _mock_full_map),
        ):
            resp = client.post("/teams/build", json={
                "players": [
                    {"game_name": "P1", "tag_line": "NA1", "role": "TOP", "champion_id": 99999},
                ],
                "platform": "NA",
            })
        assert resp.status_code == 200
        player = resp.json()["players"][0]
        assert player["champion_meta"] is None
        assert player["role_champion_fit"] == "unknown"

    @pytest.mark.integration
    def test_build_composition_archetype_engage_dive(self, client):
        """3 Tanks/Fighters + 1 Support → engage-dive archetype."""
        mock_stats = _make_team_stats_mock(["TOP", "JUNGLE", "TOP", "UTILITY", "BOTTOM"])
        with (
            patch("app.api.routes.teams.get_team_stats", mock_stats),
            patch("app.api.routes.teams.get_champion_full_map", _mock_full_map),
        ):
            resp = client.post("/teams/build", json={
                "players": [
                    {"game_name": "P1", "tag_line": "NA1", "role": "TOP",     "champion_id": 122},  # Darius - Fighter/Tank
                    {"game_name": "P2", "tag_line": "NA1", "role": "JUNGLE",  "champion_id": 64},   # Lee Sin - Fighter
                    {"game_name": "P3", "tag_line": "NA1", "role": "MIDDLE",  "champion_id": 122},  # Darius again (test only)
                    {"game_name": "P4", "tag_line": "NA1", "role": "UTILITY", "champion_id": 412},  # Thresh - Support/Tank
                    {"game_name": "P5", "tag_line": "NA1", "role": "BOTTOM",  "champion_id": 222},  # Jinx - Marksman
                ],
                "platform": "NA",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["composition_archetype"] == "engage-dive"

    @pytest.mark.integration
    def test_build_synergy_flags_present(self, client):
        """synergy_flags is always a list, even when empty."""
        mock_stats = _make_team_stats_mock(["TOP"])
        with (
            patch("app.api.routes.teams.get_team_stats", mock_stats),
            patch("app.api.routes.teams.get_champion_full_map", _mock_full_map),
        ):
            resp = client.post("/teams/build", json={
                "players": [{"game_name": "P1", "tag_line": "NA1"}],
                "platform": "NA",
            })
        assert resp.status_code == 200
        assert isinstance(resp.json()["synergy_flags"], list)

    @pytest.mark.integration
    def test_build_no_marksman_generates_synergy_flag(self, client):
        """A team with no Marksman should produce a warning synergy flag."""
        # All fighters/tanks — no Marksman tag in fixture
        mock_stats = _make_team_stats_mock(["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"])
        with (
            patch("app.api.routes.teams.get_team_stats", mock_stats),
            patch("app.api.routes.teams.get_champion_full_map", _mock_full_map),
        ):
            resp = client.post("/teams/build", json={
                "players": [
                    {"game_name": "P1", "tag_line": "NA1", "champion_id": 122},  # Darius
                    {"game_name": "P2", "tag_line": "NA1", "champion_id": 64},   # Lee Sin
                    {"game_name": "P3", "tag_line": "NA1", "champion_id": 1},    # Annie
                    {"game_name": "P4", "tag_line": "NA1", "champion_id": 412},  # Thresh
                    {"game_name": "P5", "tag_line": "NA1", "champion_id": 122},  # Darius
                ],
                "platform": "NA",
            })
        assert resp.status_code == 200
        flags = resp.json()["synergy_flags"]
        marksman_flags = [f for f in flags if "marksman" in f.lower()]
        assert len(marksman_flags) >= 1

    @pytest.mark.integration
    def test_build_composition_focus_accepted(self, client):
        """composition_focus field is accepted and echoed back in the response."""
        mock_stats = _make_team_stats_mock(["MIDDLE"])
        with (
            patch("app.api.routes.teams.get_team_stats", mock_stats),
            patch("app.api.routes.teams.get_champion_full_map", _mock_full_map),
        ):
            resp = client.post("/teams/build", json={
                "players": [
                    {"game_name": "P1", "tag_line": "NA1"},
                ],
                "platform": "NA",
                "composition_focus": "teamfight",
            })
        assert resp.status_code == 200
        assert resp.json()["composition_focus"] == "teamfight"

    @pytest.mark.integration
    def test_build_too_many_players_returns_422(self, client):
        """More than 5 players should be rejected with 422."""
        resp = client.post("/teams/build", json={
            "players": [
                {"game_name": f"P{i}", "tag_line": "NA1"} for i in range(6)
            ],
            "platform": "NA",
        })
        assert resp.status_code == 422


class TestTeamsMatchupChampionEnrichment:
    """POST /teams/matchup — champion data surfaced + role_champion_fit in per-role cards."""

    @pytest.mark.integration
    def test_matchup_returns_200_minimal(self, client):
        """Bare minimum request (no champion data) returns 200 with expected top-level shape."""
        # Mock returns 1 player — must match the 1-player request per team
        mock_stats = _make_team_stats_mock(["MIDDLE"])
        with (
            patch("app.api.routes.teams.get_team_stats", mock_stats),
            patch("app.api.routes.teams.get_champion_full_map", _mock_full_map),
        ):
            resp = client.post("/teams/matchup", json={
                "blue_team": [{"game_name": "Blue1", "tag_line": "NA1", "role": "MIDDLE"}],
                "red_team":  [{"game_name": "Red1",  "tag_line": "NA1", "role": "MIDDLE"}],
                "platform":  "NA",
            })
        assert resp.status_code == 200
        data = resp.json()
        for key in ("blue_team", "red_team", "blue_win_probability",
                    "red_win_probability", "role_matchups"):
            assert key in data, f"Expected key '{key}' missing from matchup response"

    @pytest.mark.integration
    def test_matchup_champion_meta_in_player_entries(self, client):
        """When champion_id is provided, each player entry has champion_meta."""
        mock_blue = AsyncMock(return_value=[_fake_player_stat("Faker", "MIDDLE")])
        mock_red  = AsyncMock(return_value=[_fake_player_stat("Caps",  "MIDDLE")])

        call_count = 0
        async def _alternating_stats(inputs, platform, db):
            nonlocal call_count
            result = mock_blue.return_value if call_count == 0 else mock_red.return_value
            call_count += 1
            return result

        with (
            patch("app.api.routes.teams.get_team_stats", side_effect=_alternating_stats),
            patch("app.api.routes.teams.get_champion_full_map", _mock_full_map),
        ):
            resp = client.post("/teams/matchup", json={
                "blue_team": [
                    {"game_name": "Faker", "tag_line": "T1", "role": "MIDDLE", "champion_id": 1},
                ],
                "red_team": [
                    {"game_name": "Caps", "tag_line": "EUW", "role": "MIDDLE", "champion_id": 1},
                ],
                "platform": "KR",
            })
        assert resp.status_code == 200
        data = resp.json()
        # blue_team and red_team are objects with a "players" list
        b_player = data["blue_team"]["players"][0]
        r_player = data["red_team"]["players"][0]
        assert b_player["champion_meta"] is not None
        assert r_player["champion_meta"] is not None
        assert b_player["champion_meta"]["name"] == "Annie"

    @pytest.mark.integration
    def test_matchup_role_champion_fit_in_player_entries(self, client):
        """role_champion_fit is present on every player entry."""
        mock_blue = AsyncMock(return_value=[_fake_player_stat("Blue1", "MIDDLE")])
        mock_red  = AsyncMock(return_value=[_fake_player_stat("Red1",  "MIDDLE")])

        call_count = 0
        async def _alt(inputs, platform, db):
            nonlocal call_count
            result = [mock_blue.return_value, mock_red.return_value][call_count % 2]
            call_count += 1
            return result

        with (
            patch("app.api.routes.teams.get_team_stats", side_effect=_alt),
            patch("app.api.routes.teams.get_champion_full_map", _mock_full_map),
        ):
            resp = client.post("/teams/matchup", json={
                "blue_team": [{"game_name": "B1", "tag_line": "NA1", "role": "MIDDLE", "champion_id": 1}],
                "red_team":  [{"game_name": "R1", "tag_line": "NA1", "role": "TOP",    "champion_id": 122}],
                "platform":  "NA",
            })
        assert resp.status_code == 200
        for side in ("blue_team", "red_team"):
            for player in resp.json()[side]["players"]:
                assert "role_champion_fit" in player

    @pytest.mark.integration
    def test_matchup_role_matchup_cards_present(self, client):
        """role_matchup is a non-empty list when both teams declare roles."""
        mock_blue = AsyncMock(return_value=[_fake_player_stat("B", "MIDDLE")])
        mock_red  = AsyncMock(return_value=[_fake_player_stat("R", "MIDDLE")])

        call_count = 0
        async def _alt(inputs, platform, db):
            nonlocal call_count
            result = [mock_blue.return_value, mock_red.return_value][call_count % 2]
            call_count += 1
            return result

        with (
            patch("app.api.routes.teams.get_team_stats", side_effect=_alt),
            patch("app.api.routes.teams.get_champion_full_map", _mock_full_map),
        ):
            resp = client.post("/teams/matchup", json={
                "blue_team": [{"game_name": "B", "tag_line": "NA1", "role": "MIDDLE"}],
                "red_team":  [{"game_name": "R", "tag_line": "NA1", "role": "MIDDLE"}],
                "platform":  "NA",
            })
        assert resp.status_code == 200
        assert len(resp.json()["role_matchups"]) >= 1

    @pytest.mark.integration
    def test_matchup_win_probability_sums_to_one(self, client):
        """blue_win_probability + red_win_probability must equal 1.0."""
        # 1 player per team — mock must also return exactly 1 player
        mock_stats = AsyncMock(return_value=[_fake_player_stat("P", "MIDDLE")])
        with (
            patch("app.api.routes.teams.get_team_stats", mock_stats),
            patch("app.api.routes.teams.get_champion_full_map", _mock_full_map),
        ):
            resp = client.post("/teams/matchup", json={
                "blue_team": [{"game_name": "B", "tag_line": "NA1"}],
                "red_team":  [{"game_name": "R", "tag_line": "NA1"}],
                "platform":  "NA",
            })
        assert resp.status_code == 200
        data = resp.json()
        total = round(data["blue_win_probability"] + data["red_win_probability"], 4)
        assert total == 1.0, f"Win probabilities do not sum to 1.0: {total}"
