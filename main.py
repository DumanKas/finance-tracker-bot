import asyncio
import logging
import os
from datetime import datetime, timedelta

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from database import (
    add_expence,
    add_to_subscribers,
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
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Инициализируем планировщик ОДИН раз
scheduler = AsyncIOScheduler()


@dp.message(Command("start"))
async def start_command(message: types.Message):
    add_to_subscribers(user_id=message.from_user.id)
    await message.answer(
        "Привет, я бот который считает твои финансы\n\nНажми /help чтобы посмотреть список команд"
    )


@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "📝 Список команд:\n"
        "/set_limit + [сумма] - добавить лимит \n"
        "/+ [сумма] — добавить расход\n"
        "/add [сумма] — добавить расход\n"
        "/total_week - Для проверки расходов за неделю\n"
        "/monthly_total - Для проверки расходов за месяц\n"
        "/remind [минуты] [текст] — поставить напоминание"
    )


async def send_remind(user_id: int, text: str):
    try:
        await bot.send_message(chat_id=user_id, text=f"⏰ Напоминание: {text}")
    except Exception as e:
        logging.error(f"Не удалось отправить напоминание: {e}")


@dp.message(Command("remind"))
async def remind_command(message: types.Message):
    parts = message.text.split(" ", 2)
    if len(parts) < 3:
        await message.answer("Формат: /remind 10 текст напоминания")
        return

    # Валидация на число, чтобы бот не падал
    if not parts[1].isdigit():
        await message.answer("⚠️ Укажите время в минутах целым числом!")
        return

    minutes = int(parts[1])
    text = parts[2]
    user_id = message.from_user.id

    run_time = datetime.now() + timedelta(minutes=minutes)

    # Добавляем задачу в синглтон-планировщик
    scheduler.add_job(
        send_remind, trigger="date", run_time=run_time, args=(user_id, text)
    )
    await message.answer(
        f"✅ Напоминание установлено на {minutes} мин. Я напомню тебе: {text}"
    )


@dp.message(Command("report"))
async def report_command(message: types.Message):
    user_id = int(message.from_user.id)
    report = get_sheets(user_id)

    if not report:
        await message.answer("У вас пока нет записей за этот месяц. 🤷‍♂️")
        return
    text = "📊 **Ваши расходы по категориям:**\n\n"
    for category, amount in report.items():
        text += f"🔹 {category}: {amount} тг\n"

    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("set_limit"))
async def set_limit(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2:
        return await message.answer(
            "Укажите сумму лимита, например /set_limit 5000"
        )

    if parts[1].isdigit():
        limit = int(parts[1])
        user_id = message.from_user.id
        set_daily_limit(user_id, limit)
        await message.answer(f"✅ Дневной лимит установлен: {limit} тенге.")
    else:
        await message.answer("Введи лимит числом")


@dp.message(Command("+", "add"))
async def add_command(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2:
        return await message.answer(
            "Напишите сумму и категорию (по желанию), например: /+ 500 такси"
        )

    amount_raw = parts[1]
    if not amount_raw.isdigit():
        return await message.reply("Введите сумму числом. Например /+1000 обед")

    amount = int(amount_raw)
    user_id = message.from_user.id

    category = " ".join(parts[2:]) if len(parts) > 2 else "Общее"
    add_expence(user_id, amount, category)

    total_today = get_today_total(user_id)
    limit = get_limit(user_id)
    status = ""
    if limit > 0:
        remaining = limit - total_today
        if remaining >= 0:
            status = f"\n✅ Остаток на день: {remaining} тг."
        else:
            status = f"\n⚠️ Перерасход: {abs(remaining)} тг.!"
    else:
        status = "\n💡 Лимит не установлен."

    await message.answer(
        f"✅ Записал: {amount} тг в категорию «{category}»\n"
        f"💰 Всего за сегодня: {total_today} тг.{status}"
    )


@dp.message(Command("total_week"))
async def total_week(message: types.Message):
    user_id = message.from_user.id
    result = get_weekly_total(user_id)
    if result == 0:
        await message.answer("Трат за неделю нет")
    else:
        await message.answer(
            f"📊 Ваши траты за последние 7 дней: **{result} тенге**",
            parse_mode="Markdown",
        )


async def send_weekly_report():
    subscribers = get_subscribers()
    for user_id in subscribers:
        stats = get_weekly_stat(user_id)
        total = get_weekly_total(user_id)
        if not stats and total == 0:
            continue

        text = "📊 **Итоги недели по категориям:**\n\n"
        for category, amount in stats:
            text += f"• {category} — {amount} тг\n"
        text += f"\n💰 **Итого за неделю:** `{total}` тг"

        try:
            await bot.send_message(user_id, text)
        except Exception:
            pass


@dp.message(Command("rates"))
async def get_rates(message: types.Message):
    url = "https://open.er-api.com/v6/latest/KZT"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    await message.answer("❌ Ошибка получения курса валют.")
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
                await message.answer(text, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка rates: {e}")
        await message.answer("❌ Не удалось получить курс валют.")


@dp.message(Command("weather"))
async def get_almaty_weather(message: types.Message):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=43.2565"
        "&longitude=76.9285"
        "&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
        "&timezone=Asia%2FAlmaty"
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                current_data = data["current"]
                temp = current_data["temperature_2m"]
                humidity = current_data["relative_humidity_2m"]
                wind = current_data["wind_speed_10m"]

                text = (
                    f"🌦 **Погода в Алматы прямо сейчас:**\n\n"
                    f"🌡 Температура: {temp}°C\n"
                    f"💧 Влажность: {humidity}%\n"
                    f"💨 Ветер: {wind} km/h"
                )
                await message.answer(text, parse_mode="Markdown")
            else:
                await message.answer("⚠️ Не удалось получить данные о погоде.")


# Асинхронный автопарсер через aiohttp
async def auto_parse_jobs():
    logging.info("Запуск автоматического парсинга вакансий...")
    url = "https://hh.kz/search/vacancy?text=python&area=160"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")
                    vacancies = soup.find_all(
                        "span", attrs={"data-qa": "serp-item__title-text"}
                    )
                    for vacancy in vacancies:
                        try:
                            parent_a = vacancy.find_parent("a")
                            if parent_a and "href" in parent_a.attrs:
                                full_url = "https://hh.kz" + parent_a["href"]
                                save_vacancy(vacancy.text, full_url)
                        except Exception as e:
                            logging.error(f"Ошибка сохранения вакансии: {e}")
                    logging.info(
                        "Парсинг успешно завершен, новые вакансии в базе!"
                    )
                else:
                    logging.error(
                        f"Ошибка при запросе вакансий: {response.status}"
                    )
    except Exception as e:
        logging.error(f"Ошибка сессии асинхронного парсера: {e}")


async def send_daily_vacancies():
    subscribers = get_subscribers()
    vacancies = get_new_vacancies(since_hours=6)
    if not vacancies:
        return

    text = "🔔 **Свежие Python-вакансии в Алматы за последние 6 часов!**\n\n"
    for title, url in vacancies:
        text += f"• {title} - [Перейти к вакансии]{url}\n"

    for user_id in subscribers:
        try:
            await bot.send_message(
                user_id,
                text,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
            await asyncio.sleep(0.5)
        except Exception:
            pass


@dp.message(Command("new"))
async def new_vacancies(message: types.Message):
    vacancies = get_new_vacancies()
    if vacancies:
        text = "Новые вакансии за последние 6 часов:\n\n"
        for title, url in vacancies:
            text += f"• {title} - {url}\n"
        await message.answer(text)
    else:
        await message.answer("Новых вакансий нет за последние 6 часов.")


# Асинхронная команда просмотра вакансий
@dp.message(Command("jobs"))
async def jobs_command(message: types.Message):
    url = "https://hh.kz/search/vacancy?text=python&area=160"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")
                    vacancies = soup.find_all(
                        "span", attrs={"data-qa": "serp-item__title-text"}
                    )
                    five = vacancies[:5]
                    text = "Первые 5 вакансий по запросу 'python' в Алматы:\n\n"
                    for index, vacancy in enumerate(five, start=1):
                        text += f"{index}. {vacancy.text}\n"
                    await message.answer(text)
                else:
                    await message.answer(
                        f"Ошибка при запросе вакансий: {response.status}"
                    )
    except Exception as e:
        logging.error(f"Ошибка в jobs: {e}")
        await message.answer("❌ Не удалось загрузить вакансии.")


@dp.message(Command("monthly_total"))
async def monthly_total(message: types.Message):
    user_id = message.from_user.id
    result = get_monthly_total(user_id)
    if result == 0:
        await message.answer("Трат за месяц нет")
    else:
        await message.answer(
            f"Ваши траты за месяц {result}", parse_mode="Markdown"
        )


async def main():
    database()
    create_settings_table()

    # Настройка крона и интервалов
    scheduler.add_job(
        send_weekly_report, "cron", day_of_week="mon", hour=9, minute=0
    )
    scheduler.add_job(auto_parse_jobs, "interval", hours=6)
    scheduler.start()

    asyncio.create_task(auto_parse_jobs())

    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="set_limit", description="Поставить лимит трат"),
        BotCommand(command="add", description="Добавить сумму траты"),
        BotCommand(command="total_week", description="Траты за неделю"),
        BotCommand(command="monthly_total", description="Траты за месяц"),
        BotCommand(command="new", description="Новые вакансии"),
        BotCommand(command="jobs", description="Просмотр вакансий"),
        BotCommand(
            command="weather", description="Просмотр текущей погоды Алматы"
        ),
        BotCommand(command="rates", description="Просмотр курса валют"),
        BotCommand(command="report", description="Просмотр категории затрат"),
    ])
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")