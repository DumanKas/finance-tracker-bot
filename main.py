import asyncio
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from database import (
    add_expence,
    add_expense,
    add_to_subscribers,
    CATEGORIES,
    create_settings_table,
    database,
    get_limit,
    get_monthly_total,
    get_new_vacancies,
    get_sheets,
    get_subscribers,
    get_today_total,
    get_weekly_stat,
    get_weekly_total,
    save_vacancy,
    set_daily_limit,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в переменных окружения")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

scheduler = AsyncIOScheduler(timezone="Asia/Almaty")


# ============================================================
# FSM
# ============================================================

class AddExpenseState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_category = State()


# ============================================================
# MAIN MENU BUTTON TEXTS
# Используются, чтобы отличать "пользователь нажал кнопку меню"
# от "пользователь вводит данные для текущего FSM-состояния".
# ============================================================

MAIN_MENU_BUTTONS = {
    "➕ Добавить расход",
    "📊 Статистика",
    "📅 Поиск по датам",
    "🗂 Категории",
    "⚙️ Настройки",
}


# ============================================================
# KEYBOARDS
# ============================================================

def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="➕ Добавить расход"),
                KeyboardButton(text="📊 Статистика"),
            ],
            [
                KeyboardButton(text="📅 Поиск по датам"),
                KeyboardButton(text="🗂 Категории"),
            ],
            [
                KeyboardButton(text="⚙️ Настройки"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def category_keyboard():
    buttons = []

    category_items = list(CATEGORIES.keys())

    for i in range(0, len(category_items), 2):
        row = [
            InlineKeyboardButton(
                text=category_items[i],
                callback_data=f"expense_category:{CATEGORIES[category_items[i]]}",
            )
        ]

        if i + 1 < len(category_items):
            row.append(
                InlineKeyboardButton(
                    text=category_items[i + 1],
                    callback_data=f"expense_category:{CATEGORIES[category_items[i + 1]]}",
                )
            )

        buttons.append(row)

    buttons.append(
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="expense_cancel",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cancel_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="expense_cancel",
                )
            ]
        ]
    )


# ============================================================
# START / HELP
# ============================================================

@dp.message(Command("start"))
async def start_command(message: types.Message):
    add_to_subscribers(user_id=message.from_user.id)

    today = get_today_total(message.from_user.id)
    week = get_weekly_total(message.from_user.id)

    await message.answer(
        "💰 <b>Finance Bot 2.0</b>\n\n"
        f"Сегодня: <b>{today:,} ₸</b>\n"
        f"За неделю: <b>{week:,} ₸</b>\n\n"
        "Выбери действие ниже 👇",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "📝 <b>Finance Bot 2.0</b>\n\n"
        "➕ Добавить расход — добавить трату через кнопки\n"
        "📊 Статистика — расходы сегодня, за неделю и месяц\n"
        "📅 Поиск по датам — будет добавлен следующим этапом\n"
        "🗂 Категории — статистика по категориям\n"
        "⚙️ Настройки — дневной лимит\n\n"
        "Старые команды тоже работают:\n"
        "/+ 500\n"
        "/add 500\n"
        "/total_week\n"
        "/monthly_total\n"
        "/report\n"
        "/set_limit 5000",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# ============================================================
# ADD EXPENSE — NEW INTERFACE
# ============================================================

@dp.message(lambda message: message.text == "➕ Добавить расход")
async def add_expense_start(message: types.Message, state: FSMContext):
    await state.set_state(AddExpenseState.waiting_for_amount)

    await message.answer(
        "💸 <b>Добавление расхода</b>\n\n"
        "Введи сумму расхода в тенге.\n\n"
        "Например: <code>1500</code>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )


@dp.message(AddExpenseState.waiting_for_amount)
async def process_expense_amount(message: types.Message, state: FSMContext):
    if not message.text:
        return

    # Пользователь нажал кнопку главного меню, вместо того чтобы
    # ввести сумму — сбрасываем состояние и отдаём управление
    # обычным обработчикам меню (они зарегистрированы ниже).
    if message.text in MAIN_MENU_BUTTONS:
        await state.clear()

        if message.text == "➕ Добавить расход":
            return await add_expense_start(message, state)
        elif message.text == "📊 Статистика":
            return await statistics_menu(message)
        elif message.text == "📅 Поиск по датам":
            return await date_search(message)
        elif message.text == "🗂 Категории":
            return await categories_menu(message)
        elif message.text == "⚙️ Настройки":
            return await settings_menu(message)

    amount_raw = message.text.strip().replace(" ", "").replace(",", "")

    if not amount_raw.isdigit():
        await message.answer(
            "⚠️ Введи сумму целым числом.\n\n"
            "Например: <code>1500</code>",
            parse_mode="HTML",
        )
        return

    amount = int(amount_raw)

    if amount <= 0:
        await message.answer("⚠️ Сумма должна быть больше нуля.")
        return

    if amount > 10_000_000:
        await message.answer("⚠️ Слишком большая сумма. Проверь ввод.")
        return

    await state.update_data(amount=amount)
    await state.set_state(AddExpenseState.waiting_for_category)

    await message.answer(
        f"💰 Сумма: <b>{amount:,} ₸</b>\n\n"
        "Теперь выбери категорию:",
        parse_mode="HTML",
        reply_markup=category_keyboard(),
    )


@dp.message(AddExpenseState.waiting_for_category)
async def process_expense_category_menu_interrupt(
        message: types.Message, state: FSMContext
):
    """
    Пока ждём выбора категории (через inline-кнопки), пользователь
    может нажать кнопку из ReplyKeyboard главного меню — это придёт
    сюда как обычное текстовое сообщение. Обрабатываем так же, как
    и в process_expense_amount: сбрасываем состояние и передаём
    управление нужному обработчику.
    """
    if not message.text:
        return

    if message.text in MAIN_MENU_BUTTONS:
        await state.clear()

        if message.text == "➕ Добавить расход":
            return await add_expense_start(message, state)
        elif message.text == "📊 Статистика":
            return await statistics_menu(message)
        elif message.text == "📅 Поиск по датам":
            return await date_search(message)
        elif message.text == "🗂 Категории":
            return await categories_menu(message)
        elif message.text == "⚙️ Настройки":
            return await settings_menu(message)

    await message.answer(
        "Пожалуйста, выбери категорию, нажав на одну из кнопок выше 👆",
    )


@dp.callback_query(
    AddExpenseState.waiting_for_category,
    lambda callback: callback.data.startswith("expense_category:")
)
async def process_expense_category(
        callback: types.CallbackQuery,
        state: FSMContext,
):
    category = callback.data.split(":", 1)[1]

    data = await state.get_data()
    amount = data.get("amount")

    if not amount:
        await callback.answer("Сессия добавления устарела.")
        await state.clear()
        return

    user_id = callback.from_user.id

    add_expense(
        user_id=user_id,
        amount=amount,
        category=category,
    )

    total_today = get_today_total(user_id)
    limit = get_limit(user_id)

    status = ""

    if limit > 0:
        remaining = limit - total_today

        if remaining >= 0:
            status = f"\n✅ Остаток на день: <b>{remaining:,} ₸</b>"
        else:
            status = f"\n⚠️ Перерасход: <b>{abs(remaining):,} ₸</b>"
    else:
        status = "\n💡 Дневной лимит не установлен."

    await state.clear()

    await callback.message.edit_text(
        "✅ <b>Расход добавлен!</b>\n\n"
        f"💰 Сумма: <b>{amount:,} ₸</b>\n"
        f"🗂 Категория: <b>{category}</b>\n"
        f"📅 Сегодня: <b>{total_today:,} ₸</b>"
        f"{status}",
        parse_mode="HTML",
    )

    await callback.message.answer(
        "Главное меню:",
        reply_markup=main_menu_keyboard(),
    )

    await callback.answer("Расход сохранён ✅")


@dp.callback_query(
    lambda callback: callback.data == "expense_cancel"
)
async def cancel_expense(
        callback: types.CallbackQuery,
        state: FSMContext,
):
    await state.clear()

    await callback.message.edit_text(
        "❌ Добавление расхода отменено."
    )

    await callback.message.answer(
        "Главное меню:",
        reply_markup=main_menu_keyboard(),
    )

    await callback.answer()


# ============================================================
# STATISTICS
# ============================================================

@dp.message(lambda message: message.text == "📊 Статистика")
async def statistics_menu(message: types.Message):
    user_id = message.from_user.id

    today = get_today_total(user_id)
    week = get_weekly_total(user_id)
    month = get_monthly_total(user_id)

    await message.answer(
        "📊 <b>Статистика расходов</b>\n\n"
        f"📅 Сегодня: <b>{today:,} ₸</b>\n"
        f"📆 Последние 7 дней: <b>{week:,} ₸</b>\n"
        f"🗓 Последние 30 дней: <b>{month:,} ₸</b>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# ============================================================
# CATEGORIES
# ============================================================

@dp.message(lambda message: message.text == "🗂 Категории")
async def categories_menu(message: types.Message):
    user_id = message.from_user.id
    stats = get_weekly_stat(user_id)

    if not stats:
        await message.answer(
            "🗂 <b>Категории</b>\n\n"
            "За последние 7 дней расходов пока нет.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return

    total = sum(amount for _, amount in stats)

    text = "🗂 <b>Расходы по категориям за 7 дней</b>\n\n"

    for category, amount in stats:
        percent = (amount / total * 100) if total else 0
        text += f"• {category}: <b>{amount:,} ₸</b> — {percent:.1f}%\n"

    text += f"\n💰 Всего: <b>{total:,} ₸</b>"

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# ============================================================
# DATE SEARCH — TEMPORARY STUB
# ============================================================

@dp.message(lambda message: message.text == "📅 Поиск по датам")
async def date_search(message: types.Message):
    await message.answer(
        "📅 <b>Поиск по датам</b>\n\n"
        "Эта функция будет следующим этапом.\n\n"
        "Сделаем выбор:\n"
        "• Сегодня\n"
        "• Вчера\n"
        "• Эта неделя\n"
        "• Этот месяц\n"
        "• Свой период",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# ============================================================
# SETTINGS
# ============================================================

@dp.message(lambda message: message.text == "⚙️ Настройки")
async def settings_menu(message: types.Message):
    limit = get_limit(message.from_user.id)

    if limit > 0:
        limit_text = f"{limit:,} ₸"
    else:
        limit_text = "не установлен"

    await message.answer(
        "⚙️ <b>Настройки</b>\n\n"
        f"💰 Дневной лимит: <b>{limit_text}</b>\n\n"
        "Чтобы изменить лимит:\n"
        "<code>/set_limit 5000</code>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# ============================================================
# OLD ADD COMMANDS — COMPATIBILITY
# ============================================================

@dp.message(Command("+", "add"))
async def add_command(message: types.Message):
    parts = message.text.split()

    if len(parts) < 2:
        return await message.answer(
            "Напишите сумму, например:\n"
            "<code>/+ 500</code>\n\n"
            "Или используйте кнопку ➕ Добавить расход.",
            parse_mode="HTML",
        )

    amount_raw = parts[1].replace(" ", "").replace(",", "")

    if not amount_raw.isdigit():
        return await message.reply(
            "Введите сумму числом. Например:\n"
            "<code>/+1000</code>",
            parse_mode="HTML",
        )

    amount = int(amount_raw)
    user_id = message.from_user.id

    category = " ".join(parts[2:]) if len(parts) > 2 else "Другое"

    add_expence(user_id, amount, category)

    total_today = get_today_total(user_id)
    limit = get_limit(user_id)

    status = ""

    if limit > 0:
        remaining = limit - total_today

        if remaining >= 0:
            status = f"\n✅ Остаток на день: {remaining:,} ₸"
        else:
            status = f"\n⚠️ Перерасход: {abs(remaining):,} ₸"
    else:
        status = "\n💡 Лимит не установлен."

    await message.answer(
        f"✅ Записал: {amount:,} ₸\n"
        f"🗂 Категория: «{category}»\n"
        f"💰 Всего сегодня: {total_today:,} ₸"
        f"{status}",
        reply_markup=main_menu_keyboard(),
    )


# ============================================================
# DAILY LIMIT
# ============================================================

@dp.message(Command("set_limit"))
async def set_limit(message: types.Message):
    parts = message.text.split()

    if len(parts) < 2:
        return await message.answer(
            "Укажите сумму лимита, например:\n"
            "<code>/set_limit 5000</code>",
            parse_mode="HTML",
        )

    if parts[1].isdigit():
        limit = int(parts[1])
        user_id = message.from_user.id

        set_daily_limit(user_id, limit)

        await message.answer(
            f"✅ Дневной лимит установлен: <b>{limit:,} ₸</b>.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await message.answer("Введи лимит числом.")


# ============================================================
# REPORT
# ============================================================

@dp.message(Command("report"))
async def report_command(message: types.Message):
    user_id = int(message.from_user.id)
    report = get_sheets(user_id)

    if not report:
        await message.answer(
            "У вас пока нет записей. 🤷‍♂️",
            reply_markup=main_menu_keyboard(),
        )
        return

    text = "📊 <b>Ваши расходы по категориям:</b>\n\n"

    for category, amount in report.items():
        text += f"🔹 {category}: {amount:,} ₸\n"

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# ============================================================
# WEEKLY / MONTHLY
# ============================================================

@dp.message(Command("total_week"))
async def total_week(message: types.Message):
    user_id = message.from_user.id
    result = get_weekly_total(user_id)

    if result == 0:
        await message.answer("Трат за неделю нет.")
    else:
        await message.answer(
            f"📊 Ваши траты за последние 7 дней: "
            f"<b>{result:,} ₸</b>",
            parse_mode="HTML",
        )


@dp.message(Command("monthly_total"))
async def monthly_total(message: types.Message):
    user_id = message.from_user.id
    result = get_monthly_total(user_id)

    if result == 0:
        await message.answer("Трат за месяц нет.")
    else:
        await message.answer(
            f"📊 Ваши траты за последние 30 дней: "
            f"<b>{result:,} ₸</b>",
            parse_mode="HTML",
        )


# ============================================================
# REMINDERS
# ============================================================

async def send_remind(user_id: int, text: str):
    logging.info(f"Отправляю напоминание {user_id}: {text}")

    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"⏰ Напоминание: {text}",
        )
        logging.info("Успешно отправлено")
    except Exception as e:
        logging.error(f"Не удалось отправить напоминание: {e}")


@dp.message(Command("remind"))
async def remind_command(message: types.Message):
    parts = message.text.split(" ", 2)

    if len(parts) < 3:
        await message.answer(
            "Формат:\n"
            "<code>/remind 10 текст напоминания</code>",
            parse_mode="HTML",
        )
        return

    if not parts[1].isdigit():
        await message.answer(
            "⚠️ Укажите время в минутах целым числом!"
        )
        return

    minutes = int(parts[1])
    text = parts[2]
    user_id = message.from_user.id

    run_time = datetime.now(
        tz=ZoneInfo("Asia/Almaty")
    ) + timedelta(minutes=minutes)

    scheduler.add_job(
        send_remind,
        trigger="date",
        run_date=run_time,
        args=(user_id, text),
    )

    logging.info(
        f"Джоба добавлена, run_time={run_time}, "
        f"jobs={scheduler.get_jobs()}"
    )

    await message.answer(
        f"✅ Напоминание установлено на {minutes} мин.\n"
        f"Я напомню тебе: {text}"
    )


# ============================================================
# WEEKLY REPORT
# ============================================================

async def send_weekly_report():
    subscribers = get_subscribers()

    for user_id in subscribers:
        stats = get_weekly_stat(user_id)
        total = get_weekly_total(user_id)

        if not stats and total == 0:
            continue

        text = "📊 <b>Итоги недели по категориям:</b>\n\n"

        for category, amount in stats:
            text += f"• {category} — {amount:,} ₸\n"

        text += f"\n💰 <b>Итого за неделю:</b> {total:,} ₸"

        try:
            await bot.send_message(
                user_id,
                text,
                parse_mode="HTML",
            )
        except Exception as e:
            logging.error(
                f"Ошибка отправки недельного отчёта: {e}"
            )


# ============================================================
# RATES
# ============================================================

@dp.message(Command("rates"))
async def get_rates(message: types.Message):
    url = "https://open.er-api.com/v6/latest/KZT"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    await message.answer(
                        "❌ Ошибка получения курса валют."
                    )
                    return

                data = await response.json()
                rates = data["rates"]

                usd = round(1 / rates["USD"], 2)
                eur = round(1 / rates["EUR"], 2)
                rub = round(1 / rates["RUB"], 2)

                text = (
                    "💱 <b>Курс валют к тенге</b>\n\n"
                    f"🇺🇸 1 USD = {usd} ₸\n"
                    f"🇪🇺 1 EUR = {eur} ₸\n"
                    f"🇷🇺 1 RUB = {rub} ₸"
                )

                await message.answer(
                    text,
                    parse_mode="HTML",
                )

    except Exception as e:
        logging.error(f"Ошибка rates: {e}")
        await message.answer(
            "❌ Не удалось получить курс валют."
        )


# ============================================================
# WEATHER
# ============================================================

@dp.message(Command("weather"))
async def get_almaty_weather(message: types.Message):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=43.2565"
        "&longitude=76.9285"
        "&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
        "&timezone=Asia%2FAlmaty"
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:

                if response.status == 200:
                    data = await response.json()
                    current_data = data["current"]

                    temp = current_data["temperature_2m"]
                    humidity = current_data["relative_humidity_2m"]
                    wind = current_data["wind_speed_10m"]

                    text = (
                        "🌦 <b>Погода в Алматы прямо сейчас:</b>\n\n"
                        f"🌡 Температура: {temp}°C\n"
                        f"💧 Влажность: {humidity}%\n"
                        f"💨 Ветер: {wind} km/h"
                    )

                    await message.answer(
                        text,
                        parse_mode="HTML",
                    )

                else:
                    await message.answer(
                        "⚠️ Не удалось получить данные о погоде."
                    )

    except Exception as e:
        logging.error(f"Ошибка weather: {e}")
        await message.answer(
            "❌ Не удалось получить погоду."
        )


# ============================================================
# VACANCIES PARSER
# ============================================================

async def auto_parse_jobs():
    logging.info("Запуск автоматического парсинга вакансий...")

    url = "https://hh.kz/search/vacancy?text=python&area=160"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                    url,
                    headers=headers,
            ) as response:

                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(
                        html,
                        "html.parser",
                    )

                    vacancies = soup.find_all(
                        "span",
                        attrs={
                            "data-qa": "serp-item__title-text"
                        },
                    )

                    for vacancy in vacancies:
                        try:
                            parent_a = vacancy.find_parent("a")

                            if parent_a and "href" in parent_a.attrs:
                                full_url = (
                                        "https://hh.kz"
                                        + parent_a["href"]
                                )

                                save_vacancy(
                                    vacancy.text,
                                    full_url,
                                )

                        except Exception as e:
                            logging.error(
                                f"Ошибка сохранения вакансии: {e}"
                            )

                    logging.info(
                        "Парсинг успешно завершен, "
                        "новые вакансии в базе!"
                    )

                else:
                    logging.error(
                        f"Ошибка при запросе вакансий: "
                        f"{response.status}"
                    )

    except Exception as e:
        logging.error(
            f"Ошибка сессии асинхронного парсера: {e}"
        )


async def send_daily_vacancies():
    subscribers = get_subscribers()
    vacancies = get_new_vacancies(since_hours=6)

    if not vacancies:
        return

    text = (
        "🔔 <b>Свежие Python-вакансии "
        "в Алматы за последние 6 часов!</b>\n\n"
    )

    for title, url in vacancies:
        text += f"• {title} — {url}\n"

    for user_id in subscribers:
        try:
            await bot.send_message(
                user_id,
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )

            await asyncio.sleep(0.5)

        except Exception as e:
            logging.error(
                f"Ошибка отправки вакансий: {e}"
            )


@dp.message(Command("new"))
async def new_vacancies(message: types.Message):
    vacancies = get_new_vacancies()

    if vacancies:
        text = "Новые вакансии за последние 6 часов:\n\n"

        for title, url in vacancies:
            text += f"• {title} — {url}\n"

        await message.answer(text)

    else:
        await message.answer(
            "Новых вакансий нет за последние 6 часов."
        )


@dp.message(Command("jobs"))
async def jobs_command(message: types.Message):
    url = "https://hh.kz/search/vacancy?text=python&area=160"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                    url,
                    headers=headers,
            ) as response:

                if response.status == 200:
                    html = await response.text()

                    soup = BeautifulSoup(
                        html,
                        "html.parser",
                    )

                    vacancies = soup.find_all(
                        "span",
                        attrs={
                            "data-qa": "serp-item__title-text"
                        },
                    )

                    five = vacancies[:5]

                    text = (
                        "Первые 5 вакансий по запросу "
                        "'python' в Алматы:\n\n"
                    )

                    for index, vacancy in enumerate(
                            five,
                            start=1,
                    ):
                        text += (
                            f"{index}. "
                            f"{vacancy.text}\n"
                        )

                    await message.answer(text)

                else:
                    await message.answer(
                        f"Ошибка при запросе вакансий: "
                        f"{response.status}"
                    )

    except Exception as e:
        logging.error(f"Ошибка в jobs: {e}")
        await message.answer(
            "❌ Не удалось загрузить вакансии."
        )


# ============================================================
# MAIN
# ============================================================

async def main():
    database()
    create_settings_table()

    scheduler.add_job(
        send_weekly_report,
        "cron",
        day_of_week="mon",
        hour=9,
        minute=0,
        timezone="Asia/Almaty",
    )

    scheduler.add_job(
        auto_parse_jobs,
        "interval",
        hours=6,
    )

    scheduler.start()

    asyncio.create_task(auto_parse_jobs())

    await bot.set_my_commands([
        BotCommand(
            command="start",
            description="Запуск",
        ),
        BotCommand(
            command="help",
            description="Помощь",
        ),
        BotCommand(
            command="set_limit",
            description="Поставить лимит трат",
        ),
        BotCommand(
            command="add",
            description="Добавить сумму траты",
        ),
        BotCommand(
            command="total_week",
            description="Траты за неделю",
        ),
        BotCommand(
            command="monthly_total",
            description="Траты за месяц",
        ),
        BotCommand(
            command="new",
            description="Новые вакансии",
        ),
        BotCommand(
            command="jobs",
            description="Просмотр вакансий",
        ),
        BotCommand(
            command="weather",
            description="Просмотр текущей погоды Алматы",
        ),
        BotCommand(
            command="rates",
            description="Просмотр курса валют",
        ),
        BotCommand(
            command="report",
            description="Просмотр категории затрат",
        ),
    ])

    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")
