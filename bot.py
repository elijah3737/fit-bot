import os
import asyncio
import httpx
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

BOT_TOKEN = os.environ["BOT_TOKEN"]
OLLAMA_URL = os.environ.get("OLLAMA_URL", "https://api.ollama.com").rstrip("/")
OLLAMA_TOKEN = os.environ.get("OLLAMA_TOKEN", "")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:12b")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
MINI_APP_URL = "https://elijah3737.github.io/weight-tracker/"

SYSTEM_PROMPT = """Ты — AI-бот по снижению веса.
Ты помогаешь пользователю выстраивать здоровые привычки, считать калории и следить за прогрессом.

ВАЖНО: У тебя нет имени. Никогда не называй себя "Вита", "Vita" или любым другим именем.
Если тебя спросят как тебя зовут — отвечай: "Я просто бот".

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

    # Убираем имя Вита на случай если модель всё равно его использует
    reply = reply.replace("Вита", "Бот").replace("Vita", "Бот").replace("вита", "бот")
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


async def transcribe_voice(file_bytes: bytes, filename: str) -> str:
    if not GROQ_API_KEY:
        return ""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": (filename, file_bytes, "audio/ogg")},
            data={"model": "whisper-large-v3", "language": "ru"},
        )
        resp.raise_for_status()
        return resp.json().get("text", "")


@dp.message(F.voice)
async def handle_voice(message: types.Message):
    if not GROQ_API_KEY:
        await message.answer("⚠️ Голосовые сообщения не настроены. Добавьте GROQ_API_KEY.")
        return

    await bot.send_chat_action(message.chat.id, "typing")

    try:
        file = await bot.get_file(message.voice.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(file_url)
            resp.raise_for_status()
            audio_bytes = resp.content

        text = await transcribe_voice(audio_bytes, f"{message.voice.file_id}.ogg")
        if not text:
            await message.answer("⚠️ Не удалось распознать голос. Попробуй ещё раз.")
            return

        await message.answer(f"🎤 _{text}_", parse_mode="Markdown")
        reply = await ask_ollama(message.from_user.id, text)
        await message.answer(reply)
    except httpx.HTTPStatusError as e:
        await message.answer(f"⚠️ Ошибка транскрипции: {e.response.status_code}")
    except Exception as e:
        await message.answer(f"⚠️ Что-то пошло не так: {e}")


@dp.message()
async def handle_message(message: types.Message):
    if not message.text:
        await message.answer("Пришли текстовое или голосовое сообщение — отвечу 😊")
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
