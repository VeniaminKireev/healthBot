import aiohttp
from config import OPENWEATHER_API_KEY, OPENWEATHER_URL

OPENFOODFACTS_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"

async def get_temperature_c(city: str) -> float | None:
    params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"}
    async with aiohttp.ClientSession() as session:
        async with session.get(OPENWEATHER_URL, params=params, timeout=10) as r:
            if r.status != 200:
                return None
            data = await r.json()
            return float(data["main"]["temp"])

async def search_food_kcal_100g(query: str) -> dict | None:
    params = {
        "action": "process",
        "search_terms": query,
        "json": "true",
        "page_size": 5,
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(OPENFOODFACTS_SEARCH_URL, params=params, timeout=10) as r:
            if r.status != 200:
                return None
            data = await r.json()
            products = data.get("products", [])
            # берем первый продукт с более-менее реальными ккал
            for p in products:
                nutr = p.get("nutriments", {}) or {}
                kcal = nutr.get("energy-kcal_100g")
                name = p.get("product_name") or p.get("generic_name") or query
                if kcal is not None:
                    try:
                        return {"name": str(name).strip() or query, "kcal_100g": float(kcal)}
                    except (ValueError, TypeError):
                        continue
            return None

def calc_water_goal_ml(weight_kg: float, activity_min: int, temp_c: float | None) -> int:
    """
    Базовая норма: вес * 30 мл
    + 500 мл за каждые 30 мин активности
    + 500 мл если жарко > 25°C (можно сделать 1000 при > 30°C)
    """
    base = weight_kg * 30
    activity_bonus = (activity_min // 30) * 500
    heat_bonus = 0
    if temp_c is not None and temp_c > 25:
        heat_bonus = 500 if temp_c <= 30 else 1000
    return int(base + activity_bonus + heat_bonus)

def calc_calorie_goal(weight_kg: float, height_cm: float, age: int, activity_min: int) -> int:
    """
    Упрощенная формула (без пола):
    BMR = 10*вес + 6.25*рост - 5*возраст
    Активность: +200 если >=30 мин, +300 если >=60, +400 если >=90
    """
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age
    bonus = 0
    if activity_min >= 90:
        bonus = 400
    elif activity_min >= 60:
        bonus = 300
    elif activity_min >= 30:
        bonus = 200
    return int(bmr + bonus)

def estimate_workout_kcal(workout_type: str, minutes: int) -> int:
    """
    Простейшая оценка расхода калорий:
    - бег: 10 ккал/мин
    - ходьба: 4 ккал/мин
    - вело: 8 ккал/мин
    - силовая: 6 ккал/мин
    - другое: 5 ккал/мин
    """
    t = workout_type.lower()
    if "бег" in t or "run" in t:
        kpm = 10
    elif "ход" in t or "walk" in t:
        kpm = 4
    elif "вел" in t or "bike" in t:
        kpm = 8
    elif "сил" in t or "gym" in t:
        kpm = 6
    else:
        kpm = 5
    return int(kpm * minutes)

def workout_extra_water_ml(minutes: int) -> int:
    """+200 мл за каждые 30 минут тренировки."""
    return (minutes // 30) * 200
