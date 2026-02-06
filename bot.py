import asyncio
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import BOT_TOKEN
from utils import (
    get_temperature_c,
    search_food_kcal_100g,
    calc_water_goal_ml,
    calc_calorie_goal,
    estimate_workout_kcal,
    workout_extra_water_ml,
)

router = Router()

# Хранилище в памяти
users: dict[int, dict] = {}

def ensure_user(uid: int) -> dict:
    if uid not in users:
        users[uid] = {
            "weight": None,
            "height": None,
            "age": None,
            "activity": 0,
            "city": None,
            "water_goal": None,
            "calorie_goal": None,
            "logged_water": 0,        # мл
            "logged_calories": 0,     # ккал (съедено)
            "burned_calories": 0,     # ккал (сожжено)
            "manual_calorie_goal": False,
        }
    return users[uid]

class ProfileFSM(StatesGroup):
    weight = State()
    height = State()
    age = State()
    activity = State()
    city = State()
    calorie_goal = State()

class FoodFSM(StatesGroup):
    food_name = State()
    grams = State()

@router.message(Command("start"))
async def start(message: Message):
    ensure_user(message.from_user.id)
    await message.answer(
        "Привет! Я бот для воды/калорий/тренировок.\n\n"
        "Команды:\n"
        "/set_profile — настроить профиль\n"
        "/log_water <мл> — записать воду\n"
        "/log_food <продукт> — записать еду\n"
        "/log_workout <тип> <минуты> — записать тренировку\n"
        "/check_progress — прогресс\n"
        "/help — помощь"
    )

@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "Примеры:\n"
        "/set_profile\n"
        "/log_water 300\n"
        "/log_food banana\n"
        "/log_workout бег 30\n"
        "/check_progress"
    )

# -------- Профиль --------

@router.message(Command("set_profile"))
async def set_profile(message: Message, state: FSMContext):
    ensure_user(message.from_user.id)
    await state.set_state(ProfileFSM.weight)
    await message.answer("Введите ваш вес (в кг), например: 80")

@router.message(ProfileFSM.weight)
async def prof_weight(message: Message, state: FSMContext):
    try:
        w = float(message.text.replace(",", "."))
        if w <= 0 or w > 400:
            raise ValueError
    except Exception:
        await message.answer("Вес должен быть числом (кг), например 80")
        return
    await state.update_data(weight=w)
    await state.set_state(ProfileFSM.height)
    await message.answer("Введите ваш рост (в см), например: 184")

@router.message(ProfileFSM.height)
async def prof_height(message: Message, state: FSMContext):
    try:
        h = float(message.text.replace(",", "."))
        if h <= 0 or h > 250:
            raise ValueError
    except Exception:
        await message.answer("Рост должен быть числом (см), например 184")
        return
    await state.update_data(height=h)
    await state.set_state(ProfileFSM.age)
    await message.answer("Введите ваш возраст, например: 26")

@router.message(ProfileFSM.age)
async def prof_age(message: Message, state: FSMContext):
    try:
        a = int(message.text)
        if a <= 0 or a > 120:
            raise ValueError
    except Exception:
        await message.answer("Возраст должен быть целым числом, например 26")
        return
    await state.update_data(age=a)
    await state.set_state(ProfileFSM.activity)
    await message.answer("Сколько минут активности у вас в день? Например: 45")

@router.message(ProfileFSM.activity)
async def prof_activity(message: Message, state: FSMContext):
    try:
        act = int(message.text)
        if act < 0 or act > 1000:
            raise ValueError
    except Exception:
        await message.answer("Активность должна быть целым числом минут, например 45")
        return
    await state.update_data(activity=act)
    await state.set_state(ProfileFSM.city)
    await message.answer("В каком городе вы находитесь? Например: Moscow / Berlin")

@router.message(ProfileFSM.city)
async def prof_city(message: Message, state: FSMContext):
    city = (message.text or "").strip()
    if not city:
        await message.answer("Введите город текстом, например Moscow")
        return

    data = await state.get_data()
    uid = message.from_user.id
    u = ensure_user(uid)

    u["weight"] = data["weight"]
    u["height"] = data["height"]
    u["age"] = data["age"]
    u["activity"] = data["activity"]
    u["city"] = city

    temp = await get_temperature_c(city)
    water_goal = calc_water_goal_ml(u["weight"], u["activity"], temp)
    calorie_goal = calc_calorie_goal(u["weight"], u["height"], u["age"], u["activity"])

    u["water_goal"] = water_goal

    # спросим: хочешь ли вручную цель калорий?
    u["calorie_goal"] = calorie_goal
    u["manual_calorie_goal"] = False

    await state.set_state(ProfileFSM.calorie_goal)
    weather_line = f"Температура в {city}: {temp:.1f}°C" if temp is not None else f"Погода для {city} недоступна"
    await message.answer(
        f"Профиль сохранен.\n"
        f"{weather_line}\n\n"
        f"Рассчитано:\n"
        f"💧 Норма воды: {water_goal} мл/день\n"
        f"🔥 Норма калорий: {calorie_goal} ккал/день\n\n"
        f"Хотите задать цель калорий вручную? Введите число (например 2500) или напишите 'нет'."
    )

@router.message(ProfileFSM.calorie_goal)
async def prof_cal_goal(message: Message, state: FSMContext):
    uid = message.from_user.id
    u = ensure_user(uid)
    txt = (message.text or "").strip().lower()

    if txt in {"нет", "no", "n"}:
        await message.answer("Ок! Используем рассчитанную цель. Можно начинать логировать 🙂")
        await state.clear()
        return

    try:
        goal = int(txt)
        if goal < 800 or goal > 6000:
            raise ValueError
    except Exception:
        await message.answer("Введите число (например 2500) или 'нет'.")
        return

    u["calorie_goal"] = goal
    u["manual_calorie_goal"] = True
    await message.answer(f"Ок! Цель калорий установлена: {goal} ккал/день.")
    await state.clear()

# -------- Лог воды --------

@router.message(Command("log_water"))
async def log_water(message: Message):
    uid = message.from_user.id
    u = ensure_user(uid)

    if u["water_goal"] is None:
        await message.answer("Сначала настройте профиль: /set_profile")
        return

    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Формат: /log_water <мл>\nНапример: /log_water 300")
        return
    try:
        ml = int(parts[1])
        if ml <= 0 or ml > 5000:
            raise ValueError
    except Exception:
        await message.answer("Количество воды должно быть числом в мл, например 300")
        return

    u["logged_water"] += ml
    left = max(0, u["water_goal"] - u["logged_water"])
    await message.answer(
        f"💧 Записано: {ml} мл.\n"
        f"Выпито: {u['logged_water']} мл из {u['water_goal']} мл.\n"
        f"Осталось: {left} мл."
    )

# -------- Лог еды --------

@router.message(Command("log_food"))
async def log_food_start(message: Message, state: FSMContext):
    uid = message.from_user.id
    u = ensure_user(uid)
    if u["calorie_goal"] is None:
        await message.answer("Сначала настройте профиль: /set_profile")
        return

    query = message.text.replace("/log_food", "", 1).strip()
    if not query:
        await message.answer("Формат: /log_food <название>\nНапример: /log_food banana")
        return

    info = await search_food_kcal_100g(query)
    if not info:
        await message.answer(
            "Не нашёл продукт в OpenFoodFacts 😕\n"
            "Попробуйте на английском (banana, apple, yogurt) или более общее название."
        )
        return

    await state.update_data(food_name=info["name"], kcal_100g=info["kcal_100g"])
    await state.set_state(FoodFSM.grams)
    await message.answer(
        f"🍽 {info['name']} — {info['kcal_100g']} ккал на 100 г.\n"
        "Сколько грамм вы съели?"
    )

@router.message(FoodFSM.grams)
async def log_food_grams(message: Message, state: FSMContext):
    uid = message.from_user.id
    u = ensure_user(uid)

    try:
        grams = float(message.text.replace(",", "."))
        if grams <= 0 or grams > 5000:
            raise ValueError
    except Exception:
        await message.answer("Введите граммы числом, например: 150")
        return

    data = await state.get_data()
    kcal_100g = float(data["kcal_100g"])
    food_name = data["food_name"]
    eaten_kcal = kcal_100g * grams / 100.0

    u["logged_calories"] += eaten_kcal
    left = max(0, u["calorie_goal"] - (u["logged_calories"] - u["burned_calories"]))

    await message.answer(
        f"✅ Записано: {food_name}, {grams:.0f} г = {eaten_kcal:.1f} ккал.\n"
        f"Всего съедено: {u['logged_calories']:.1f} ккал.\n"
        f"С учётом тренировок осталось до цели: {left:.1f} ккал."
    )
    await state.clear()

# -------- Лог тренировки --------

@router.message(Command("log_workout"))
async def log_workout(message: Message):
    uid = message.from_user.id
    u = ensure_user(uid)
    if u["calorie_goal"] is None or u["water_goal"] is None:
        await message.answer("Сначала настройте профиль: /set_profile")
        return

    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer("Формат: /log_workout <тип> <минуты>\nНапример: /log_workout бег 30")
        return

    try:
        minutes = int(parts[-1])
        if minutes <= 0 or minutes > 1000:
            raise ValueError
    except Exception:
        await message.answer("Минуты должны быть целым числом, например 30")
        return

    workout_type = " ".join(parts[1:-1])
    burned = estimate_workout_kcal(workout_type, minutes)
    extra_water = workout_extra_water_ml(minutes)

    u["burned_calories"] += burned
    u["water_goal"] += extra_water

    await message.answer(
        f"🏃‍♂️ {workout_type} {minutes} минут — {burned} ккал.\n"
        f"💧 Дополнительно к норме воды: +{extra_water} мл."
    )

# -------- Прогресс --------

@router.message(Command("check_progress"))
async def check_progress(message: Message):
    uid = message.from_user.id
    u = ensure_user(uid)
    if u["water_goal"] is None or u["calorie_goal"] is None:
        await message.answer("Сначала настройте профиль: /set_profile")
        return

    water_left = max(0, u["water_goal"] - u["logged_water"])
    net_kcal = u["logged_calories"] - u["burned_calories"]
    kcal_left = max(0, u["calorie_goal"] - net_kcal)

    await message.answer(
        "📊 Прогресс:\n\n"
        "Вода:\n"
        f"- Выпито: {u['logged_water']} мл из {u['water_goal']} мл.\n"
        f"- Осталось: {water_left} мл.\n\n"
        "Калории:\n"
        f"- Потреблено: {u['logged_calories']:.1f} ккал из {u['calorie_goal']} ккал.\n"
        f"- Сожжено: {u['burned_calories']:.1f} ккал.\n"
        f"- Баланс: {net_kcal:.1f} ккал.\n"
        f"- Осталось до цели: {kcal_left:.1f} ккал."
    )

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
