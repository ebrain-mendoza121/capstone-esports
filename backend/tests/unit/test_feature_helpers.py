"""
Unit tests for pure helper functions in feature_extractor.py

Tests:
  _linear_trend     — slope calculation for trend analysis
  _compute_streak   — consecutive win/loss streak
  _encode_patch     — patch version string to float
"""

import pytest
from app.services.feature_extractor import (
    _linear_trend,
    _compute_streak,
    _encode_patch,
)


# ---------------------------------------------------------------------------
# _linear_trend
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestLinearTrend:

    def test_upward_trend_returns_positive_slope(self):
        """Steadily improving values should return a positive slope."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        slope = _linear_trend(values)
        assert slope > 0, "Upward trend must yield positive slope"

    def test_downward_trend_returns_negative_slope(self):
        """Declining values should return a negative slope."""
        values = [5.0, 4.0, 3.0, 2.0, 1.0]
        slope = _linear_trend(values)
        assert slope < 0, "Downward trend must yield negative slope"

    def test_flat_trend_returns_zero(self):
        """Constant values should return slope of 0."""
        values = [3.5, 3.5, 3.5, 3.5]
        slope = _linear_trend(values)
        assert slope == pytest.approx(0.0, abs=1e-9)

    def test_single_value_returns_zero(self):
        """Fewer than 2 points — cannot fit a line, returns 0."""
        assert _linear_trend([4.0]) == 0.0

    def test_empty_list_returns_zero(self):
        """Empty list should return 0.0 safely."""
        assert _linear_trend([]) == 0.0

    def test_slope_magnitude(self):
        """Verify the slope is numerically correct: y = x gives slope = 1.0."""
        values = [0.0, 1.0, 2.0, 3.0, 4.0]
        slope = _linear_trend(values)
        assert slope == pytest.approx(1.0, rel=0.01)


# ---------------------------------------------------------------------------
# _compute_streak
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestComputeStreak:

    def test_win_streak(self):
        """Three consecutive wins returns +3."""
        results = [True, True, True, False, True]
        assert _compute_streak(results) == 3

    def test_loss_streak(self):
        """Three consecutive losses returns -3."""
        results = [False, False, False, True]
        assert _compute_streak(results) == -3

    def test_single_win(self):
        """One win with no prior returns +1."""
        assert _compute_streak([True]) == 1

    def test_single_loss(self):
        """One loss returns -1."""
        assert _compute_streak([False]) == -1

    def test_empty_list(self):
        """Empty list should return 0."""
        assert _compute_streak([]) == 0

    def test_alternating_starts_with_win(self):
        """Win then loss: streak is only 1."""
        results = [True, False, True, False]
        assert _compute_streak(results) == 1

    def test_alternating_starts_with_loss(self):
        """Loss then win: streak is only -1."""
        results = [False, True, False, True]
        assert _compute_streak(results) == -1

    def test_long_win_streak(self):
        """Ten consecutive wins returns +10."""
        results = [True] * 10
        assert _compute_streak(results) == 10


# ---------------------------------------------------------------------------
# _encode_patch
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEncodePatch:

    def test_standard_patch(self):
        """Patch '14.8.1' should encode to 14.08."""
        assert _encode_patch("14.8.1") == pytest.approx(14.08, rel=0.001)

    def test_double_digit_minor(self):
        """Patch '14.10.1' should encode to 14.10."""
        assert _encode_patch("14.10.1") == pytest.approx(14.10, rel=0.001)

    def test_none_returns_zero(self):
        """None input returns 0.0 safely."""
        assert _encode_patch(None) == 0.0

    def test_empty_string_returns_zero(self):
        """Empty string returns 0.0 safely."""
        assert _encode_patch("") == 0.0

    def test_malformed_patch_returns_zero(self):
        """Unrecognizable patch string returns 0.0 without raising."""
        assert _encode_patch("not_a_patch") == 0.0

    def test_newer_patch(self):
        """Patch '16.5.1' should encode to 16.05."""
        result = _encode_patch("16.5.1")
        assert result == pytest.approx(16.05, rel=0.001)
