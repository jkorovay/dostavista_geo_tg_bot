import asyncio
import logging
import re
import os
from typing import Optional, List, Tuple

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder
from dotenv import load_dotenv
import aiohttp
from aiohttp_retry import RetryClient, ExponentialRetry
from aiolimiter import AsyncLimiter
import redis.asyncio as redis

from config import (
    BOT_TOKEN,
    GRAPHHOPPER_API_KEY,
    FUEL_CONSUMPTION,
    FUEL_PRICE,
    MIN_HOURLY_RATE,
    WAIT_TIME_MINUTES,
    DEFAULT_START_ADDR,
    HTTP_TIMEOUT,
    RETRY_ATTEMPTS,
    RETRY_BASE_DELAY,
    GRAPHHOPPER_RPS,
    REDIS_URL,
    LOG_LEVEL,
    LOG_FILE,
    LOG_MAX_BYTES,
    LOG_BACKUP_COUNT,
)
from logging_config import setup_logging, get_logger
from circuit_breaker import graphhopper_breaker, CircuitOpenError

# --- Настройка логирования ---
setup_logging(level=LOG_LEVEL, log_file=LOG_FILE, json_format=False)
log = get_logger(__name__)

# --- Константы API ---
GRAPHHOPPER_GEOCODE_URL = "https://graphhopper.com/api/1/geocode"
GRAPHHOPPER_ROUTE_URL = "https://graphhopper.com/api/1/route"

# --- Redis & FSM Storage ---
redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
storage = RedisStorage(redis_client, key_builder=DefaultKeyBuilder(with_bot_id=True))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)


class OrderForm(StatesGroup):
    waiting_for_start = State()
    waiting_for_pickup = State()
    waiting_for_delivery = State()
    waiting_for_price = State()


# --- HTTP-КЛИЕНТ С RETRY + RATE LIMIT ---

async def create_http_client() -> RetryClient:
    """
    Создаёт RetryClient с:
    - ExponentialRetry: 3 попытки, базовая задержка 0.5 сек
    - Rate limiter: токен-бакет (RPS)
    - Общий timeout 15 сек
    """
    retry_options = ExponentialRetry(
        attempts=RETRY_ATTEMPTS,
        start_timeout=RETRY_BASE_DELAY,
        max_timeout=8.0,
        factor=2.0,
        statuses={429, 500, 502, 503, 504},
        exceptions={aiohttp.ClientError, asyncio.TimeoutError},
    )

    limiter = AsyncLimiter(GRAPHHOPPER_RPS)

    class RateLimitedClient(RetryClient):
        async def _request(self, method, url, **kwargs):
            async with limiter:
                return await super()._request(method, url, **kwargs)

    client = RateLimitedClient(
        retry_options=retry_options,
        timeout=HTTP_TIMEOUT,
        raise_for_status=False,
    )
    return client


async def close_http_client(client: RetryClient):
    await client.close()


# --- GRAPHHOPPER API ---

@graphhopper_breaker
async def geocode_address(client: RetryClient, address: str) -> Optional[List[float]]:
    """Ищет координаты по адресу через GraphHopper Geocoding API."""
    params = {"q": address, "locale": "ru", "key": GRAPHHOPPER_API_KEY, "limit": 1}
    try:
        async with client.get(GRAPHHOPPER_GEOCODE_URL, params=params) as resp:
            if resp.status != 200:
                text = await resp.text()
                log.error(f"Geocode HTTP {resp.status}: {text[:200]}")
                return None
            data = await resp.json()
            if data.get('hits'):
                point = data['hits'][0]['point']
                result = [point['lng'], point['lat']]
                log.info(f"Geocoded '{address}' -> {result}")
                return result
    except CircuitOpenError:
        log.error(f"Circuit OPEN - GraphHopper geocode unavailable for '{address}'")
        raise
    except Exception as e:
        log.error(f"Geocoding error for '{address}': {e}")
    return None


@graphhopper_breaker
async def calculate_route(client: RetryClient, coords_list: List[List[float]]) -> Tuple[Optional[float], Optional[float]]:
    """Считает маршрут через GraphHopper Routing API. Возвращает (dist_km, duration_min)."""
    params = {
        "key": GRAPHHOPPER_API_KEY,
        "vehicle": "car",
        "locale": "ru",
        "calc_points": "false",
        "instructions": "false",
    }
    points = "&".join(f"point={lat},{lon}" for lon, lat in coords_list)
    url = f"{GRAPHHOPPER_ROUTE_URL}?{points}&" + "&".join(f"{k}={v}" for k, v in params.items())

    try:
        async with client.get(url) as resp:
            if resp.status != 200:
                text = await resp.text()
                log.error(f"Route HTTP {resp.status}: {text[:200]}")
                return None, None
            data = await resp.json()

            if 'paths' in data and data['paths']:
                path = data['paths'][0]
                dist_km = path['distance'] / 1000.0
                duration_min = path['time'] / 60000.0
                log.info(f"Route: {dist_km:.1f} km, {duration_min:.1f} min")
                return dist_km, duration_min
            else:
                log.error(f"No paths in response: {data}")
    except CircuitOpenError:
        log.error("Circuit OPEN - GraphHopper route unavailable")
        raise
    except Exception as e:
        log.error(f"Route error: {e}")
    return None, None


# --- УТИЛИТЫ ---

def parse_coordinates(text: str) -> Optional[List[float]]:
    """Извлекает координаты из текста: 55.814273,37.456615"""
    matches = re.findall(r'(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)', text)
    for match in matches:
        lat = float(match[0])
        lon = float(match[1])
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            log.info(f"Parsed coords: lat={lat}, lon={lon}")
            return [lon, lat]
    return None


async def get_coords(client: RetryClient, address: str) -> Optional[List[float]]:
    """Пробует распарсить координаты, иначе геокодит через GraphHopper."""
    coords = parse_coordinates(address)
    if coords:
        return coords
    return await geocode_address(client, address)


# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="📍 Я на Кронштадтском")],
            [types.KeyboardButton(text="🗺 Геопозиция", request_location=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Где ты сейчас?", reply_markup=kb)
    await state.set_state(OrderForm.waiting_for_start)


@dp.message(OrderForm.waiting_for_start)
async def process_start(message: types.Message, state: FSMContext):
    http = dp["http"]
    coords = None

    if message.location:
        coords = [message.location.longitude, message.location.latitude]
    elif "Кронштадтском" in message.text:
        coords = await get_coords(http, DEFAULT_START_ADDR)
    else:
        coords = await get_coords(http, message.text)

    if not coords:
        await message.answer("❌ Не нашёл адрес. Попробуй ещё раз.")
        return

    await state.update_data(start_coords=coords)
    await message.answer("✅ Принято. Введи адрес точки А (забор груза):",
                         reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(OrderForm.waiting_for_pickup)


@dp.message(OrderForm.waiting_for_pickup)
async def process_pickup(message: types.Message, state: FSMContext):
    http = dp["http"]
    coords = await get_coords(http, message.text)
    if not coords:
        await message.answer("❌ Не нашёл. Попробуй координаты (55.123,37.456)")
        return

    await state.update_data(pickup_coords=coords)
    await message.answer("✅ Точка А есть. Введи адрес точки Б (доставка):")
    await state.set_state(OrderForm.waiting_for_delivery)


@dp.message(OrderForm.waiting_for_delivery)
async def process_delivery(message: types.Message, state: FSMContext):
    http = dp["http"]
    coords = await get_coords(http, message.text)
    if not coords:
        await message.answer("❌ Не нашёл адрес.")
        return

    await state.update_data(delivery_coords=coords)
    await message.answer("💰 Цена заказа (руб)?")
    await state.set_state(OrderForm.waiting_for_price)


@dp.message(OrderForm.waiting_for_price)
async def process_calc(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(',', '.').replace(' ', ''))
    except ValueError:
        await message.answer("Введи число.")
        return

    data = await state.get_data()
    msg = await message.answer("⏳ Считаю...")

    route = [data['start_coords'], data['pickup_coords'], data['delivery_coords']]
    log.info(f"Route points: {route}")

    http = dp["http"]
    dist_km, duration_min = await calculate_route(http, route)

    if not dist_km:
        await msg.edit_text("❌ Ошибка API. Проверь ключ GraphHopper.")
        await state.clear()
        return

    total_time = duration_min + WAIT_TIME_MINUTES
    fuel_cost = (dist_km / 100.0) * FUEL_CONSUMPTION * FUEL_PRICE
    net = price - fuel_cost
    hourly = (net / (total_time / 60.0)) if total_time > 0 else 0

    # --- РЕЙТИНГ ---
    if hourly < 500:
        rating_emoji, rating_text, verdict = "🔴", "НЕ БЕРЕМ", "❌"
    elif 500 <= hourly < 700:
        rating_emoji, rating_text, verdict = "🟠", "БЕРЕМ, НО ДУМАЕМ", "⚠️"
    elif 700 <= hourly < 1000:
        rating_emoji, rating_text, verdict = "🟢", "БЕРЕМ! ОТЛИЧНО", "✅"
    else:
        rating_emoji, rating_text, verdict = "🟡", "НЕВИДАННАЯ ЩЕДРОСТЬ!", "💎"

    result = (
        f"{verdict} {rating_emoji} **{rating_text}**\n\n"
        f"🛣 **Маршрут:** {dist_km:.1f} км\n"
        f"⏱ **Время:** {int(duration_min)} мин + {WAIT_TIME_MINUTES} мин = {int(total_time)} мин\n"
        f"⛽ **Бензин:** -{int(fuel_cost)} ₽\n"
        f"💵 **Чистыми:** {int(net)} ₽\n"
        f"📊 **Ставка:** {int(hourly)} ₽/ч\n\n"
        f"_Лимит: {int(MIN_HOURLY_RATE)} ₽/ч_"
    )

    await msg.edit_text(result, parse_mode="Markdown")
    await message.answer("Новый расчёт: /start")
    await state.clear()


# --- LIFECYCLE ---

async def on_startup(dispatcher: Dispatcher):
    """Создаём общий HTTP-клиент при старте и кладем в dp['http']."""
    client = await create_http_client()
    dispatcher["http"] = client
    log.info("HTTP client created with retry + rate limit")
    log.info("Redis FSM storage ready")


async def on_shutdown(dispatcher: Dispatcher):
    """Закрываем HTTP-клиент и Redis при остановке."""
    client = dispatcher.get("http")
    if client:
        await close_http_client(client)
        log.info("HTTP client closed")
    await redis_client.close()
    await redis_client.connection_pool.disconnect()
    log.info("Redis connection closed")


async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())