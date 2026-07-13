"""
Async-friendly Circuit Breaker для внешних API вызовов.

Кастомная реализация, не зависящая от pybreaker async support.
"""
import asyncio
import logging
import time
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, Set, TypeVar

from logging_config import get_logger

log = get_logger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Вызывается когда circuit breaker открыт и вызов отклонён."""


class AsyncCircuitBreaker:
    """
    Простая async реализация circuit breaker.

    Usage:
        breaker = AsyncCircuitBreaker(
            fail_max=5,
            reset_timeout=60,
            exclude={asyncio.TimeoutError},
        )

        @breaker
        async def call_graphhopper(...):
            ...

    Или через call():
        result = await breaker.call(func, *args, **kwargs)
    """

    def __init__(
        self,
        fail_max: int = 5,
        reset_timeout: int = 60,
        exclude: Optional[Set[type]] = None,
        name: str = "circuit_breaker",
    ):
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.exclude = exclude or {asyncio.TimeoutError}
        self.name = name

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        # Проверяем переход из OPEN в HALF_OPEN
        if self._state == CircuitState.OPEN:
            if self._last_failure_time and self.reset_timeout > 0:
                if time.time() - self._last_failure_time >= self.reset_timeout:
                    self._state = CircuitState.HALF_OPEN
            # Если reset_timeout == 0, остаёмся в OPEN до ручного reset
        return self._state.value

    async def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Выполняет функцию с защитой circuit breaker."""
        async with self._lock:
            current_state = self.state

            if current_state == CircuitState.OPEN.value:
                log.warning(f"[{self.name}] Circuit OPEN - failing fast")
                raise CircuitOpenError(f"{self.name} circuit is OPEN")

        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                self._on_success()
            return result
        except Exception as e:
            if type(e) in self.exclude:
                # Исключённые исключения не считаются как ошибки
                raise
            async with self._lock:
                self._on_failure()
            raise

    def _on_success(self):
        """Обработка успешного вызова."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def _on_failure(self):
        """Обработка неудачного вызова."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._failure_count >= self.fail_max:
            self._state = CircuitState.OPEN
            log.warning(f"[{self.name}] Circuit OPENED after {self._failure_count} failures")

    def reset(self):
        """Ручное закрытие circuit breaker."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._last_failure_time = None

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Поддержка @breaker декоратора."""
        return with_breaker(self)(func)


def with_breaker(breaker: AsyncCircuitBreaker):
    """Декоратор для применения конкретного breaker к async функции."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await breaker.call(func, *args, **kwargs)
        return wrapper
    return decorator


# --- Предконфигурированные breakers для наших сервисов ---

graphhopper_breaker = AsyncCircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    exclude={asyncio.TimeoutError},
    name="graphhopper",
)

redis_breaker = AsyncCircuitBreaker(
    fail_max=3,
    reset_timeout=30,
    exclude={ConnectionError, TimeoutError},
    name="redis",
)