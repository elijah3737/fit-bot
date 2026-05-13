import os
import asyncio
import base64
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

FOOD_PHOTO_PROMPT = """Ты — нутрициолог. На фото еда. Определи все видимые блюда и продукты, рассчитай КБЖУ для каждого.
Ответь по-русски в таком формате:

🍽 *Что вижу:*
- Блюдо 1 — X ккал (Б: Xг, Ж: Xг, У: Xг)
- Блюдо 2 — X ккал (Б: Xг, Ж: Xг, У: Xг)

📊 *Итого:* X ккал | Б: Xг | Ж: Xг | У: Xг

Если вес порции неизвестен — используй стандартную порцию. Добавь короткий комментарий: укладывается ли приём пищи в норму ~1800 ккал/день."""

SYSTEM_PROMPT = """Ты — персональный AI-нутрициолог и коуч по снижению веса в Telegram.
Твой стиль: тёплый, но конкретный. Как умный друг с медицинским образованием — не читаешь лекций, не осуждаешь, но даёшь реальные советы.

## Онбординг
Если пользователь пишет впервые или после /reset — задай 2–3 вопроса, чтобы персонализировать советы:
- Какова цель? (похудеть / удержать вес / набрать мышцы)
- Текущий вес и желаемый (примерно)
- Есть ли ограничения: аллергии, вегетарианство, болезни?
Запомни ответы и опирайся на них в дальнейшем разговоре.

## Как отвечать
- По-русски, без воды
- Короткие сообщения (2–5 предложений) для простых вопросов
- Структурированные ответы с эмодзи-маркерами для планов и списков
- Если вопрос про еду — всегда указывай КБЖУ на 100г и на порцию
- Используй *жирный* и _курсив_ для акцентов (Telegram Markdown)

## Сценарии поведения

**Пользователь сорвался:**
Не осуждай. Нормализуй ("это случается со всеми"), найди причину срыва, предложи конкретный шаг на сегодня.

**Просит посчитать калории:**
Назови КБЖУ, сравни с суточной нормой (считай ~1800 ккал если норма неизвестна), скажи укладывается ли в цель.

**Просит план питания:**
Дай конкретный план на день с приёмами пищи. Реалистичный — без экзотики.

**Мотивация упала:**
Короткий заряжающий ответ + один маленький конкретный шаг прямо сейчас.

## Ограничения
- Не ставь диагнозы и не отменяй назначения врача
- Если вопрос совсем не по теме — мягко верни к теме здоровья
- Если не знаешь точное КБЖУ — скажи приблизительно и предупреди

## Кто ты
У тебя нет имени. Если спросят — "Я просто бот". Никогда не называй себя Вита или любым другим именем."""

# История сообщений по user_id (в памяти, до 20 сообщений)
history: dict[int, list] = {}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def ask_ollama_with_image(base64_image: str) -> str:
    headers = {"Content-Type": "application/json"}
    if OLLAMA_TOKEN:
        headers["Authorization"] = f"Bearer {OLLAMA_TOKEN}"

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{
            "role": "user",
            "content": FOOD_PHOTO_PROMPT,
            "images": [base64_image],
        }],
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()["message"]["content"]


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


@dp.message(F.photo)
async def handle_photo(message: types.Message):
    await bot.send_chat_action(message.chat.id, "typing")

    try:
        # Берём фото в наивысшем качестве (последний элемент — самый большой)
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(file_url)
            resp.raise_for_status()
            image_bytes = resp.content

        b64 = base64.b64encode(image_bytes).decode()
        reply = await ask_ollama_with_image(b64)
        await message.answer(reply, parse_mode="Markdown")
    except httpx.HTTPStatusError as e:
        await message.answer(f"⚠️ Ошибка анализа фото: {e.response.status_code}")
    except Exception as e:
        await message.answer(f"⚠️ Что-то пошло не так: {e}")


@dp.message()
async def handle_message(message: types.Message):
    if not message.text:
        await message.answer("Пришли текстовое, голосовое сообщение или фото еды — отвечу 😊")
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
