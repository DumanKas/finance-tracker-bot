from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import BotCommand
import logging
logging.basicConfig(level=logging.INFO)
import asyncio
import os
from database import database,add_expence,get_today_total,get_weekly_total,get_monthly_total,create_settings_table,get_limit,set_daily_limit
from dotenv import load_dotenv
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command('start'))
async def start_command(message: types.Message):
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
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="set_limit",description="Поставить лимит трат"),
        BotCommand(command='add',description="Добавить сумму траты"),
        BotCommand(command='total_week',description="Траты за неделю"),
        BotCommand(command="monthly_total",description="Траты за месяц")
    ])
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")