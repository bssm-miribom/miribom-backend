import redis

from app.core.config import settings

r = redis.Redis.from_url(settings.redis_url, decode_responses=True)

LATEST_KEY = "miribom:latest"
LOCK_KEY = "miribom:daily-lock"
