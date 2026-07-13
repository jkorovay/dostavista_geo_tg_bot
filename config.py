# --- КОНФИГ ---
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN not found in .env")
    exit(1)

# GraphHopper
GRAPHHOPPER_API_KEY = os.getenv("GRAPHHOPPER_API_KEY")
if not GRAPHHOPPER_API_KEY:
    print("❌ GRAPHHOPPER_API_KEY not found in .env")
    exit(1)

# Настройки расчёта
FUEL_CONSUMPTION = float(os.getenv("FUEL_CONSUMPTION", "9.5"))
FUEL_PRICE = float(os.getenv("FUEL_PRICE", "70.0"))
MIN_HOURLY_RATE = float(os.getenv("MIN_HOURLY_RATE", "500.0"))
WAIT_TIME_MINUTES = int(os.getenv("WAIT_TIME_MINUTES", "15"))
DEFAULT_START_ADDR = os.getenv("DEFAULT_START_ADDR", "55.8516018,37.5130927")

# Настройки HTTP-клиента
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)
HTTP_RETRY_ATTEMPTS = int(os.getenv("HTTP_RETRY_ATTEMPTS", "3"))
HTTP_RETRY_BASE_DELAY = float(os.getenv("HTTP_RETRY_BASE_DELAY", "0.5"))
GRAPHHOPPER_RPS = float(os.getenv("GRAPHHOPPER_RPS", "2"))

# Aliases for backward compatibility with bot.py imports
RETRY_ATTEMPTS = HTTP_RETRY_ATTEMPTS
RETRY_BASE_DELAY = HTTP_RETRY_BASE_DELAY

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Логирование
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "logs/bot.log")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "5_000_000"))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "3"))

# Константы API
GRAPHHOPPER_GEOCODE_URL = "https://graphhopper.com/api/1/geocode"
GRAPHHOPPER_ROUTE_URL = "https://graphhopper.com/api/1/route"