import asyncio
import json
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument

from config import BOT_TOKEN, REPORT_CHAT_ID, TIMEZONE_OFFSET

# === Настройки ===
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()
db_path = "db.json"

# === База ===
def load_db():
    if os.path.exists(db_path):
        with open(db_path, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_db(data):
    with open(db_path, "w") as f:
        json.dump(data, f, indent=2)

# === /start ===
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    db = load_db()
    user_id = str(message.from_user.id)
    if user_id not in db:
        db[user_id] = {
            "username": message.from_user.username or "-",
            "name": message.from_user.full_name,
            "report_sent": False
        }
        save_db(db)
    await message.answer("Привет! Отправь сюда свой ежедневный отчёт одним сообщением.")

# === Отчёты ===
@dp.message()
async def report_handler(message: types.Message):
    db = load_db()
    user_id = str(message.from_user.id)
    if user_id in db:
        db[user_id]["report_sent"] = True
        save_db(db)

        caption = f"📨 Отчёт от @{db[user_id]['username']} ({db[user_id]['name']})"

        if message.text:
            await bot.send_message(REPORT_CHAT_ID, f"{caption}\n\n{message.text}")
        elif message.photo:
            await bot.send_photo(REPORT_CHAT_ID, message.photo[-1].file_id, caption=caption)
        elif message.video:
            await bot.send_video(REPORT_CHAT_ID, message.video.file_id, caption=caption)
        elif message.document:
            await bot.send_document(REPORT_CHAT_ID, message.document.file_id, caption=caption)
        else:
            await bot.send_message(REPORT_CHAT_ID, caption)

        await message.answer("Отчёт принят. Спасибо!")
    else:
        await message.answer("Вы не зарегистрированы. Напишите /start.")

# === Напоминания ===
async def send_reminders():
    now = datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)
    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Задача send_reminders() активна")

    day_of_week = now.weekday()  # Пн = 0, Вс = 6
    if day_of_week == 6:
        print("Воскресенье — напоминания отключены")
        return

    hour = now.hour
    minute = now.minute

    db = load_db()
    for uid, data in db.items():
        if not data.get("report_sent", False):
            try:
                # Финальное напоминание в 23:30
                if hour == 23 and minute == 30:
                    await bot.send_message(
                        uid,
                        "⚠️ Финальное предупреждение! Если отчёт не будет отправлен до 00:00, "
                        "завтра руководителю будет передана задача провести с вами беседу по поводу невовремя сданного отчёта."
                    )
                # Обычные напоминания с 19:00 до 22:00 (каждый час)
                elif hour in range(19, 23) and minute == 0:
                    await bot.send_message(uid, "⏰ Вижу, что ты не отправил ещё ежедневный отчёт о проделанной работе за день. НЕ забудь его отправить!")
                    print(f"✅ Напоминание отправлено: {uid}")
            except Exception as e:
                print(f"❌ Ошибка отправки напоминания {uid}: {e}")

# === Проверка после 00:00 ===
async def final_check():
    print("[00:01] Запуск проверки отчётов")
    db = load_db()
    for uid, data in db.items():
        if not data.get("report_sent", False):
            text = f"❌ @{data['username']} ({data['name']}) не отправил отчёт до 00:00. Поручение: провести беседу."
            await bot.send_message(REPORT_CHAT_ID, text)
        db[uid]["report_sent"] = False  # Сброс на следующий день
    save_db(db)

# === Планировщик ===
# Напоминания с 19:00 до 22:00 каждый час
scheduler.add_job(send_reminders, "cron", hour="19-22", minute=0, day_of_week="0-5")
# Финальное предупреждение в 23:30
scheduler.add_job(send_reminders, "cron", hour=23, minute=30, day_of_week="0-5")
# Проверка после 00:00
scheduler.add_job(final_check, "cron", hour=0, minute=1)

# === Старт ===
async def main():
    print("✅ Бот запущен.")
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
