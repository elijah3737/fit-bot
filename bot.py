import os
import asyncio
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

BOT_TOKEN = os.environ["BOT_TOKEN"]
OLLAMA_URL = os.environ.get("OLLAMA_URL", "https://api.ollama.com").rstrip("/")
OLLAMA_TOKEN = os.environ.get("OLLAMA_TOKEN", "")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:12b")
MINI_APP_URL = "https://elijah3737.github.io/weight-tracker/"

SYSTEM_PROMPT = """Ты — AI-бот по снижению веса.
Ты помогаешь пользователю выстраивать здоровые привычки, считать калории и следить за прогрессом.
Не называй себя никаким именем — ты просто бот.

Правила:
- Отвечай по-русски, коротко и по делу
- Не осуждай срывы — поддерживай и помогай вернуться в режим
- Давай конкретные советы, основанные на науке
- При вопросах про еду — называй КБЖУ если знаешь
- Держись темы: здоровое питание, похудение, привычки, мотивация
- Используй эмодзи умеренно"""

# История сообщений по user_id (в памяти, до 20 сообщений)
history: dict[int, list] = {}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def ask_ollama(user_id: int, user_message: str) -> str:
    msgs = history.setdefault(user_id, [])
    msgs.append({"role": "user", "content": user_message})
    # Ограничиваем историю последними 20 сообщениями
    if len(msgs) > 20:
        msgs[:] = msgs[-20:]

    headers = {"Content-Type": "application/json"}
    if OLLAMA_TOKEN:
        headers["Authorization"] = f"Bearer {OLLAMA_TOKEN}"

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + msgs,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload, headers=headers)
        resp.raise_for_status()
        reply = resp.json()["message"]["content"]

    msgs.append({"role": "assistant", "content": reply})
    return reply


def tracker_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📊 Открыть трекер",
            web_app=WebAppInfo(url=MINI_APP_URL)
        )
    ]])


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    name = message.from_user.first_name or "друг"
    await message.answer(
        f"Привет, {name}! 👋\n\n"
        "Я бот по снижению веса.\n"
        "Помогу с питанием, привычками и мотивацией.\n\n"
        "Просто напиши мне что угодно, или открой трекер 👇",
        reply_markup=tracker_button(),
    )


@dp.message(Command("tracker"))
async def cmd_tracker(message: types.Message):
    await message.answer("Открывай трекер 👇", reply_markup=tracker_button())


@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    history.pop(message.from_user.id, None)
    await message.answer("История очищена. Начинаем заново! 🔄")


@dp.message()
async def handle_message(message: types.Message):
    if not message.text:
        await message.answer("Пришли текстовое сообщение — отвечу 😊")
        return

    # Показываем что печатаем
    await bot.send_chat_action(message.chat.id, "typing")

    try:
        reply = await ask_ollama(message.from_user.id, message.text)
        await message.answer(reply)
    except httpx.HTTPStatusError as e:
        await message.answer(f"⚠️ Ошибка Ollama: {e.response.status_code}")
    except Exception as e:
        await message.answer(f"⚠️ Что-то пошло не так: {e}")


async def main():
    print(f"Bot started. Model: {OLLAMA_MODEL}, Ollama: {OLLAMA_URL}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
