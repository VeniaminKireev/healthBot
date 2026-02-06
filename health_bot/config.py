import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env")
if not OPENWEATHER_API_KEY:
    raise RuntimeError("OPENWEATHER_API_KEY is not set in .env")
