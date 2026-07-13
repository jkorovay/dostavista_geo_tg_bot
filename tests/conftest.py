"""
Test configuration and fixtures.
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis

# Set dummy env vars BEFORE importing bot
os.environ.setdefault("BOT_TOKEN", "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef")
os.environ.setdefault("GRAPHHOPPER_API_KEY", "test_graphhopper_key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bot import (
    parse_coordinates,
    calculate_route,
    geocode_address,
    get_coords,
    create_http_client,
    close_http_client,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def fake_redis():
    """Fake Redis for testing FSM storage."""
    redis = FakeAsyncRedis(decode_responses=True)
    yield redis
    await redis.close()


@pytest_asyncio.fixture
async def http_client():
    """Test HTTP client with retry + rate limit."""
    client = await create_http_client()
    yield client
    await close_http_client(client)


@pytest.fixture
def mock_graphhopper_geocode():
    """Mock GraphHopper geocode response."""
    return {
        "hits": [{
            "point": {"lat": 55.7558, "lng": 37.6173},
            "name": "Moscow",
            "osm_value": "city",
            "country": "Russia",
        }]
    }


@pytest.fixture
def mock_graphhopper_route():
    """Mock GraphHopper route response."""
    return {
        "paths": [{
            "distance": 15000.0,  # meters
            "time": 900000.0,      # milliseconds
            "points": {"coordinates": [[37.6173, 55.7558], [37.6200, 55.7600]]},
        }]
    }