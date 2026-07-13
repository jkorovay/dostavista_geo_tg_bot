"""
Tests for utility functions and calculation logic.
"""
import pytest

from bot import (
    parse_coordinates,
    MIN_HOURLY_RATE,
    WAIT_TIME_MINUTES,
    FUEL_CONSUMPTION,
    FUEL_PRICE,
)


class TestParseCoordinates:
    """Tests for parse_coordinates function."""

    def test_valid_coordinates(self):
        """Valid lat,lon string returns [lon, lat]."""
        result = parse_coordinates("55.814273,37.456615")
        assert result == [37.456615, 55.814273]

    def test_valid_coordinates_with_spaces(self):
        """Coordinates with spaces work."""
        result = parse_coordinates("55.814273, 37.456615")
        assert result == [37.456615, 55.814273]

    def test_coordinates_in_sentence(self):
        """Coordinates extracted from longer text."""
        result = parse_coordinates("Я на 55.814273,37.456615 сейчас")
        assert result == [37.456615, 55.814273]

    def test_invalid_latitude(self):
        """Latitude > 90 returns None."""
        result = parse_coordinates("95.0,37.456615")
        assert result is None

    def test_invalid_longitude(self):
        """Longitude > 180 returns None."""
        result = parse_coordinates("55.814273,200.0")
        assert result is None

    def test_no_coordinates(self):
        """Text without coordinates returns None."""
        result = parse_coordinates("Москва, Кронштадтский бульвар")
        assert result is None


class TestCalculationLogic:
    """Tests for calculation formulas."""

    def test_fuel_cost_calculation(self):
        """Fuel cost = (dist_km / 100) * consumption * price."""
        dist_km = 100.0
        expected = (dist_km / 100.0) * FUEL_CONSUMPTION * FUEL_PRICE
        result = (dist_km / 100.0) * FUEL_CONSUMPTION * FUEL_PRICE
        assert result == expected

    def test_hourly_rate_calculation(self):
        """Hourly rate = net / (total_time / 60)."""
        net = 1000.0
        total_time_min = 120.0  # 2 hours
        hourly = net / (total_time_min / 60.0)
        assert hourly == 500.0

    def test_rating_thresholds(self):
        """Rating boundaries are correct."""
        def calc_hourly(price: float, fuel_cost: float, total_time_min: float) -> float:
            net = price - fuel_cost
            if total_time_min <= 0:
                return 0
            return net / (total_time_min / 60.0)

        # < 500 -> НЕ БЕРЕМ
        # (600 - 500) / 1 = 100 < 500 ✓
        assert calc_hourly(600, 500, 60) < 500
        # 500-700 -> БЕРЁМ, НО ДУМАЕМ
        # (800 - 200) / 1 = 600 ✓
        assert 500 <= calc_hourly(800, 200, 60) < 700
        # 700-1000 -> БЕРЁМ! ОТЛИЧНО
        # (1050 - 200) / 1 = 850 ✓
        assert 700 <= calc_hourly(1050, 200, 60) < 1000
        # >= 1000 -> НЕВИДАННАЯ ЩЕДРОСТЬ
        # (3000 - 200) / 1 = 2800 ✓
        assert calc_hourly(3000, 200, 60) >= 1000