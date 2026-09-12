import base64
import hashlib
import hmac
import logging
import os
import sys
from pathlib import Path

import requests
import telebot
from flask import Flask, request
from telebot import util


# ============================================================
# НАСТРОЙКИ
# ============================================================

PUBLIC_URL = "https://radju-bot.onrender.com"
CHAT_URL = "https://api.proxyapi.ru/v1/chat/completions"
CHAT_MODEL = "x-ai/grok-4.5"

# Новые ключи берутся из Render → Environment.
# Вставлять их в этот файл не нужно.
TELEGRAM_TOKEN ="8804377859:AAHybYDorTb9c4j-o90D2tHYr_x2NNo0qaE" os.environ.get("TELEGRAM_TOKEN", "").strip()
API_KEY ="sk-w7178jSfKD6ttClL6jKlJ67BPKfJDmZL" os.environ.get("API_KEY", "").strip()

if not TELEGRAM_TOKEN:
    raise RuntimeError(
        "Добавь новый TELEGRAM_TOKEN в Render → Environment."
    )

if not API_KEY:
    raise RuntimeError(
        "Добавь новый API_KEY в Render → Environment."
    )

# Секрет вебхука рассчитывается автоматически.
# Дополнительную переменную в Render создавать не нужно.
WEBHOOK_SECRET = hmac.new(
    TELEGRAM_TOKEN.encode("utf-8"),
    b"radju-telegram-webhook-v1",
    hashlib.sha256,
).hexdigest()

MAX_IMAGE_BYTES = 10 * 1024 * 1024
DOCUMENT_PATH = Path(__file__).resolve().parent / "document.xlsx"

# Необязательно: Telegram user ID через запятую.
# Если переменная не задана, бот доступен всем.
ALLOWED_USER_IDS = {
    int(value.strip())
    for value in os.environ.get("ALLOWED_USER_IDS", "").split(",")
    if value.strip()
}

SYSTEM_PROMPT = """
Ты — ИИ-помощник по имени Раджу. Имя Раджу не склоняется.
Ты мужского пола.

Общайся дружелюбно, внимательно и поддерживающе.
Отвечай по-русски, если пользователь не просит другой язык.
Давай понятные и полезные ответы.
Не выдумывай факты, результаты действий или доступные возможности.

В этой версии приложения доступны:
- текстовые запросы;
- передача изображений для анализа, если API их поддерживает;
- отправка заранее подготовленного документа средствами приложения.

Распознавание речи, голосовые ответы, чтение PDF/Word,
создание файлов и постоянная память пока не подключены.
Не утверждай, что выполнил такие действия.

Каждый запрос обрабатывается отдельно.
Используй преимущественно обычный текст без сложной Markdown-разметки.
"""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("radju")

bot = telebot.TeleBot(
    TELEGRAM_TOKEN,
    threaded=True,
    num_threads=4,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

class UserError(Exception):
    """Сообщение об ошибке, которое можно показать пользователю."""


def send_text(chat_id, text):
    """Отправка без ошибок Markdown и превышения длины."""
    text = str(text).strip() or "Получен пустой ответ."

    for part in util.smart_split(text, chars_per_string=2000):
        bot.send_message(chat_id, part)


def is_allowed(message):
    if not ALLOWED_USER_IDS:
        return True

    if (
        message.from_user
        and message.from_user.id in ALLOWED_USER_IDS
    ):
        return True

    send_text(message.chat.id, "Доступ к этому боту ограничен.")
    return False


def download_image(file_id, file_size=None):
    if file_size and file_size > MAX_IMAGE_BYTES:
        raise UserError("Пришли изображение размером до 10 МБ.")

    file_info = bot.get_file(file_id)

    if (
        file_info.file_size
        and file_info.file_size > MAX_IMAGE_BYTES
    ):
        raise UserError("Изображение превышает лимит 10 МБ.")

    # Правильное скачивание через Telegram Bot API.
    image_bytes = bot.download_file(file_info.file_path)

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise UserError("Изображение превышает лимит 10 МБ.")

    return image_bytes


def ask_grok(text, image_bytes=None, image_mime="image/jpeg"):
    if image_bytes is None:
        user_content = text
    else:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        user_content = [
            {
                "type": "text",
                "text": text,
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": (
                        f"data:{image_mime};base64,{encoded}"
                    )
                },
            },
        ]

    payload = {
        "model": CHAT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
    }

    try:
        response = requests.post(
            CHAT_URL,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=(15, 120),
        )
    except requests.Timeout:
        raise UserError(
            "ProxyAPI не ответил вовремя. Попробуй ещё раз."
        ) from None
    except requests.RequestException:
        raise UserError(
            "Не удалось подключиться к ProxyAPI."
        ) from None

    if not response.ok:
        # Не выводим сырые ответы API и секреты в переписку.
        logger.warning(
            "ProxyAPI вернул HTTP %s",
            response.status_code,
        )

        if response.status_code == 401:
            explanation = "Проверь новый API_KEY в Render."
        elif response.status_code == 402:
            explanation = "Проверь баланс в ProxyAPI."
        elif response.status_code == 403:
            explanation = "Проверь доступ ключа к выбранной модели."
        elif response.status_code == 429:
            explanation = (
                "Превышен лимит запросов или квота. "
                "Проверь ограничения ProxyAPI."
            )
        elif image_bytes is not None and response.status_code in (
            400, 404, 415, 422
        ):
            explanation = (
                "Запрос с изображением не принят. "
                "Нужно проверить поддержку изображений "
                "и формат запроса для этого маршрута ProxyAPI."
            )
        elif response.status_code >= 500:
            explanation = "Временная ошибка сервиса. Попробуй позже."
        else:
            explanation = (
                "Проверь доступность модели и API в кабинете ProxyAPI."
            )

        raise UserError(
            f"ProxyAPI: ошибка {response.status_code}.\n{explanation}"
        )

    try:
        data = response.json()
    except ValueError:
        raise UserError(
            "ProxyAPI вернул ответ не в формате JSON."
        ) from None

    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise UserError(
            "ProxyAPI вернул неожиданный формат ответа."
        ) from None

    if not isinstance(answer, str) or not answer.strip():
        raise UserError("Модель не вернула текстовый ответ.")

    return answer.strip()


def check_for_file_request(message, text):
    triggers = (
        "скинь файл",
        "отправь документ",
        "дай таблицу",
    )

    if not any(trigger in text.lower() for trigger in triggers):
        return False

    if not DOCUMENT_PATH.is_file():
        send_text(
            message.chat.id,
            "Готовый документ пока не загружен на сервер. "
            "Для этой команды нужен файл document.xlsx "
            "рядом с bot.py. Самостоятельное создание таблиц "
            "в этой версии ещё не подключено.",
        )
        return True

    with DOCUMENT_PATH.open("rb") as document:
        bot.send_document(
            message.chat.id,
            document,
            caption="Вот документ по твоему запросу.",
        )

    return True


# ============================================================
# TELEGRAM
# ============================================================

@bot.message_handler(commands=["start", "help"])
def handle_start(message):
    if not is_allowed(message):
        return

    send_text(
        message.chat.id,
        "Привет! Я Раджу, твой ИИ-помощник.\n\n"
        "Напиши вопрос или отправь фотографию с подписью. "
        "Можно также прислать изображение файлом: JPEG, PNG или WebP.\n\n"
        "Я использую Grok через ProxyAPI. "
        "Анализ фото зависит от поддержки изображений у API.\n\n"
        "Голосовые функции и память переписки пока не подключены.\n"
        "Текст и изображения передаются в ProxyAPI для обработки.",
    )


@bot.message_handler(commands=["voice"])
def handle_voice_command(message):
    if not is_allowed(message):
        return

    send_text(
        message.chat.id,
        "Голосовые ответы пока не подключены. "
        "Для них нужен подтверждённый сервис синтеза речи. "
        "Обычные вопросы можно отправлять текстом.",
    )


@bot.message_handler(content_types=["voice", "audio"])
def handle_audio(message):
    if not is_allowed(message):
        return

    send_text(
        message.chat.id,
        "Я получил аудиосообщение, но распознавание речи "
        "пока не подключено. Напиши вопрос текстом.\n\n"
        "Само аудио сейчас не отправляется в ProxyAPI.",
    )


@bot.message_handler(content_types=["text", "photo", "document"])
def handle_message(message):
    if not is_allowed(message):
        return

    chat_id = message.chat.id

    try:
        image_bytes = None
        image_mime = "image/jpeg"

        if message.content_type == "photo":
            photo = message.photo[-1]
            image_bytes = download_image(
                photo.file_id,
                photo.file_size,
            )
            text = (
                message.caption
                or "Подробно опиши, что изображено на фотографии."
            )

        elif message.content_type == "document":
            document = message.document
            image_mime = (document.mime_type or "").lower()

            if image_mime not in (
                "image/jpeg",
                "image/png",
                "image/webp",
            ):
                raise UserError(
                    "Сейчас я принимаю изображения JPEG, PNG и WebP. "
                    "Чтение PDF, Word и таблиц ещё не подключено."
                )

            image_bytes = download_image(
                document.file_id,
                document.file_size,
            )
            text = (
                message.caption
                or "Подробно опиши это изображение."
            )

        else:
            text = (message.text or "").strip()

            if not text:
                raise UserError("Отправь непустое сообщение.")

            if check_for_file_request(message, text):
                return

        bot.send_chat_action(chat_id, "typing")

        answer = ask_grok(
            text,
            image_bytes=image_bytes,
            image_mime=image_mime,
        )
        send_text(chat_id, answer)

    except UserError as error:
        send_text(chat_id, str(error))

    except Exception as error:
        # Записываем только тип ошибки, без ключей и URL с токеном.
        logger.error(
            "Ошибка обработки сообщения: %s",
            type(error).__name__,
        )

        try:
            send_text(
                chat_id,
                "Не удалось обработать сообщение. "
                "Попробуй ещё раз. Если ошибка повторится, "
                "проверь журнал Render.",
            )
        except Exception:
            logger.error("Не удалось отправить сообщение об ошибке.")


# ============================================================
# WEBHOOK
# ============================================================

@app.get("/")
@app.get("/health")
def health():
    return "Radju bot is running", 200


@app.post("/webhook")
def webhook():
    received_secret = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token",
        "",
    )

    if not hmac.compare_digest(
        received_secret.encode("utf-8"),
        WEBHOOK_SECRET.encode("utf-8"),
    ):
        return "Forbidden", 403

    data = request.get_json(silent=True)

    if (
        not isinstance(data, dict)
        or not isinstance(data.get("update_id"), int)
    ):
        return "Bad request", 400

    try:
        update = telebot.types.Update.de_json(data)
    except Exception:
        return "Bad request", 400

    try:
        bot.process_new_updates([update])
    except Exception:
        logger.error("Не удалось принять обновление Telegram.")
        return "Internal error", 500

    return "OK", 200


def install_webhook():
    # При замене токена удаляем накопившиеся старые обновления.
    # Внимание: сообщения, ожидающие обработки во время запуска,
    # будут отброшены.
    result = bot.set_webhook(
        url=f"{PUBLIC_URL}/webhook",
        secret_token=WEBHOOK_SECRET,
        allowed_updates=["message"],
        drop_pending_updates=True,
    )

    if not result:
        raise RuntimeError("Telegram не подтвердил установку вебхука.")

    logger.info("Вебхук Раджу установлен.")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "set-webhook":
        try:
            install_webhook()
        except Exception as error:
            logger.error(
                "Ошибка установки вебхука: %s. "
                "Проверь TELEGRAM_TOKEN и доступность Telegram.",
                type(error).__name__,
            )
            sys.exit(1)
    else:
        print(
            "Запускай приложение командой из render.yaml "
            "или через gunicorn."
        )
