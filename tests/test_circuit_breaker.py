"""
Tests for Circuit Breaker.
"""
import asyncio
import pytest

from circuit_breaker import (
    AsyncCircuitBreaker,
    CircuitOpenError,
    graphhopper_breaker,
    redis_breaker,
    with_breaker,
)


class TestAsyncCircuitBreaker:
    """Tests for AsyncCircuitBreaker."""

    @pytest.mark.asyncio
    async def test_allows_successful_calls(self):
        """Successful calls pass through."""
        breaker = AsyncCircuitBreaker(fail_max=3, reset_timeout=1)

        @breaker
        async def success_func():
            return "ok"

        result = await success_func()
        assert result == "ok"
        assert breaker.state == "closed"

    @pytest.mark.asyncio
    async def test_opens_after_fail_max(self):
        """Circuit opens after fail_max failures."""
        breaker = AsyncCircuitBreaker(fail_max=2, reset_timeout=60)

        @breaker
        async def fail_func():
            raise Exception("API error")

        # First failure
        with pytest.raises(Exception):
            await fail_func()
        assert breaker.state == "closed"

        # Second failure - should open
        with pytest.raises(Exception):
            await fail_func()
        assert breaker.state == "open"

        # Third call - should fail fast with CircuitOpenError
        with pytest.raises(CircuitOpenError):
            await fail_func()

    @pytest.mark.asyncio
    async def test_excludes_specified_exceptions(self):
        """Excluded exceptions don't count as failures."""
        breaker = AsyncCircuitBreaker(
            fail_max=2,
            reset_timeout=60,
            exclude={asyncio.TimeoutError},
        )

        @breaker
        async def timeout_func():
            raise asyncio.TimeoutError("timeout")

        # Timeouts should not count as failures
        with pytest.raises(asyncio.TimeoutError):
            await timeout_func()
        with pytest.raises(asyncio.TimeoutError):
            await timeout_func()

        # Circuit should still be closed
        assert breaker.state == "closed"

    @pytest.mark.asyncio
    async def test_resets_after_timeout(self):
        """Circuit half-opens after reset_timeout."""
        breaker = AsyncCircuitBreaker(fail_max=1, reset_timeout=1)  # 1 second reset

        @breaker
        async def fail_func():
            raise Exception("error")

        # Fail once - opens
        with pytest.raises(Exception):
            await fail_func()
        assert breaker.state == "open"

        # Wait for reset timeout
        await asyncio.sleep(1.1)

        # Next call goes to half-open, if success -> closed
        @breaker
        async def success_func():
            return "ok"

        result = await success_func()
        assert result == "ok"
        assert breaker.state == "closed"

    @pytest.mark.asyncio
    async def test_manual_reset(self):
        """Manual reset closes the circuit."""
        breaker = AsyncCircuitBreaker(fail_max=1, reset_timeout=60)

        @breaker
        async def fail_func():
            raise Exception("error")

        with pytest.raises(Exception):
            await fail_func()
        assert breaker.state == "open"

        breaker.reset()
        assert breaker.state == "closed"


class TestPreconfiguredBreakers:
    """Tests for pre-configured breakers."""

    def test_graphhopper_breaker_config(self):
        """GraphHopper breaker has correct config."""
        assert graphhopper_breaker.fail_max == 5
        assert graphhopper_breaker.reset_timeout == 60
        assert asyncio.TimeoutError in graphhopper_breaker.exclude

    def test_redis_breaker_config(self):
        """Redis breaker has correct config."""
        assert redis_breaker.fail_max == 3
        assert redis_breaker.reset_timeout == 30


class TestWithBreakerDecorator:
    """Tests for with_breaker decorator."""

    @pytest.mark.asyncio
    async def test_decorator_applies_breaker(self):
        """Decorator applies specified breaker."""
        breaker = AsyncCircuitBreaker(fail_max=2, reset_timeout=60)

        @with_breaker(breaker)
        async def test_func():
            raise Exception("fail")

        with pytest.raises(Exception):
            await test_func()
        with pytest.raises(Exception):
            await test_func()

        assert breaker.state == "open"

        with pytest.raises(CircuitOpenError):
            await test_func()