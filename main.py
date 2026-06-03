from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import BotCommand
import logging

from pyexpat.errors import messages

logging.basicConfig(level=logging.INFO)
import asyncio
import os
import requests
from bs4 import BeautifulSoup

from database import (
    database, add_expence, get_today_total, get_weekly_total,
    get_monthly_total, create_settings_table, get_limit,
    set_daily_limit, get_weekly_stat, get_subscribers, add_to_subscribers,save_vacancy,get_new_vacancies
)
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
scheduler = AsyncIOScheduler()
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command('start'))
async def start_command(message: types.Message):
    add_to_subscribers(user_id=message.from_user.id)
    await message.answer("Привет, я бот который считает твой финансы\n\nНажми /help чтобы посмотреть список команд")

@dp.message(Command('help'))
async def help_command(message: types.Message):
    await message.answer("📝 Список команд:\n/set_limit + [сумма] - добавить лимит \n/+ [сумма] — добавить расход\n/add [сумма] — добавить расход\n/total_week - Для проверки расходов за неделю\n /monthly_total - Для проверки расходов за месяц")


@dp.message(Command('set_limit'))
async def set_limit(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2:
        return await message.answer("Укажите сумму лимита, например /set_limit 5000")

    if parts[1].isdigit():
        limit = int(parts[1])
        user_id = message.from_user.id
        set_daily_limit(user_id, limit)
        await message.answer(f"✅ Дневной лимит установлен: {limit} тенге.")
    else:
        await message.answer("Введи лимит числом")
@dp.message(Command('+','add'))
async def add_command(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2:
        return await message.answer("Напишите сумму и категорию (по желанию), например: /+ 500 такси")

    amount_raw = parts[1]
    if not amount_raw.isdigit():
        return await message.reply("Введите сумму числом. Например /+1000 обед")

    amount = int(amount_raw)
    user_id = message.from_user.id

    category = " ".join(parts[2:]) if len(parts) > 2 else "Общее"
    add_expence(user_id, amount,category)

    total_today = get_today_total(user_id)
    limit = get_limit(user_id)
    status = ''
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
@dp.message(Command('total_week'))
async def total_week(message: types.Message):
    user_id = message.from_user.id
    result = get_weekly_total(user_id)
    if result == 0:
        await message.answer("Трат за неделю нет")
    else:
        await message.answer(f'📊 Ваши траты за последние 7 дней: **{result} тенге**', parse_mode="Markdown")




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
            await bot.send_message(user_id,text)
        except Exception as e:
            pass


@dp.message(Command('weather'))
async def get_almaty_weather(message: types.Message):
    url = ("https://api.open-meteo.com/v1/forecast"
        "?latitude=43.2565"
        "&longitude=76.9285"
        "&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
        "&timezone=Asia%2FAlmaty")


    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        current_data = data['...']
        temp = current_data['...']
        humidity = current_data['relative-humidity_2m']
        wind = current_data['wind_speed_10m']

        text = (
            f"🌦 **Погода в Алматы прямо сейчас:**\n\n"
            f"🌡 Температура: {temp}°C\n"
            f"💧 Влажность: {humidity}%\n"
            f"💨 Ветер: {wind} km/h"
        )
        await message.answer(text, parse_mode="Markdown")

    else:
        await message.answer("⚠️ Не удалось получить данные о погоде.")

async def auto_parse_jobs():
    logging.info('Запуск автоматического парсинга вакансий...')
    url = 'https://hh.kz/search/vacancy?text=python&area=160'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        vacancies = soup.find_all(
            'span', attrs={'data-qa': 'serp-item__title-text'}
        )
        for vacancy in vacancies:
            try:
                # Находим родительскую ссылку, чтобы вытащить href
                parent_a = vacancy.find_parent('a')
                if parent_a and 'href' in parent_a.attrs:
                    full_url = 'https://hh.kz' + parent_a['href']
                    save_vacancy(vacancy.text, full_url)
            except Exception as e:
                logging.error(f'Ошибка сохранения вакансии: {e}')
        logging.info('Парсинг успешно завершен, новые вакансии в базе!')
    else:
        logging.error(f'Ошибка при запросе вакансий: {response.status_code}')




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
            await bot.send_message(user_id,text,parse_mode="Markdown",disable_web_page_preview=True)
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
@dp.message(Command("jobs"))
async def jobs_command(message: types.Message):
    url = "https://hh.kz/search/vacancy?text=python&area=160"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        vacancies = soup.find_all("span", attrs={"data-qa": "serp-item__title-text"})
        five = vacancies[:5]
        text = "Первые 5 вакансий по запросу 'python' в Алматы:\n\n"
        for index, vacancy in enumerate(five, start=1):
            text += f"{index}. {vacancy.text}\n"
        await message.answer(text)
    else:
        await message.answer(f"Ошибка при запросе вакансий: {response.status_code}")
@dp.message(Command('monthly_total'))
async def monthly_total(message: types.Message):
    user_id = message.from_user.id
    result = get_monthly_total(user_id)
    if result == 0:
        await message.answer("Трат за месяц нет")
    else:
        await message.answer(f'Ваши траты за месяц {result}',parse_mode="Markdown")
async def main():
    database()
    create_settings_table()
    scheduler.add_job(
        send_weekly_report, 'cron', day_of_week='mon', hour=9, minute=0
    )
    scheduler.add_job(auto_parse_jobs, 'interval', hours=6)
    scheduler.start()

    # Сразу при запуске бота один раз парсим вакансии, чтобы база не была пустой
    asyncio.create_task(auto_parse_jobs())
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="set_limit",description="Поставить лимит трат"),
        BotCommand(command='add',description="Добавить сумму траты"),
        BotCommand(command='total_week',description="Траты за неделю"),
        BotCommand(command="monthly_total",description="Траты за месяц"),
        BotCommand(command="new",description="Новые вакаснии"),
        BotCommand(command='jobs', description="Просмотр вакансии"),
        BotCommand(command='weather', description="Просмотр текущей погоды Алматы")
    ])
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")