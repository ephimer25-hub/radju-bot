import os
import logging
import httpx
import asyncio
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Считывание переменных окружения Render
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
PROXY_API_KEY = os.getenv("PROXY_API_KEY")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
PORT = int(os.getenv("PORT", 8443))
AITUNNEL_URL = "https://api.proxyapi.ru/v1/chat/completions"
WHISPER_URL = "https://api.proxyapi.ru/v1/audio/transcriptions"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Привет! Я Раджу, ваш ИИ-агент на базе Grok 4.5. Я умею читать текст, анализировать фото и слушать голосовые сообщения! Чем могу помочь?')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Просто отправьте мне текст, фотографию или запишите голосовое сообщение — и я отвечу вам.')

# Общая функция для отправки запросов в Grok 4.5 через ProxyAPI
async def ask_grok(messages_payload: list) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                AITUNNEL_URL,  
                headers={
                    'Authorization': f'Bearer {PROXY_API_KEY}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'x-ai/grok-4.5',  # Идентификатор Grok 4.5 в ProxyAPI
                    'messages': messages_payload
                }
            )
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                logger.error(f"Ошибка ProxyAPI: {response.status_code} - {response.text}")
                return 'Извините, произошла ошибка при обращении к нейросети.'
        except Exception as e:
            logger.error(f"Ошибка при связи с ProxyAPI: {e}")
            return 'Не удалось связаться с сервером ИИ.'

# Обработка ТЕКСТА
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    payload = [{'role': 'user', 'content': user_message}]
    reply = await ask_grok(payload)
    await update.message.reply_text(reply)

# Обработка ИЗОБРАЖЕНИЙ (Зрение Grok 4.5)
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Берем фото в самом высоком качестве
    photo_file = await update.message.photo[-1].get_file()
    caption = update.message.caption or "Что изображено на этой фотографии?"
    
    # Скачиваем фото в память приложения
    photo_bytes = await photo_file.download_as_bytearray()
    base64_image = base64.b64encode(photo_bytes).decode('utf-8')
    
    # Формируем мультимодальный запрос для Grok 4.5
    payload = [
        {
            'role': 'user',
            'content': [
                {'type': 'text', 'text': caption},
                {
                    'type': 'image_url',
                    'image_url': {'url': f"data:image/jpeg;base64,{base64_image}"}
                }
            ]
        }
    ]
    
    reply = await ask_grok(payload)
    await update.message.reply_text(reply)

# Обработка ГОЛОСОВЫХ СООБЩЕНИЙ (через Whisper)
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    voice_file = await update.message.voice.get_file()
    voice_bytes = await voice_file.download_as_bytearray()
    
    # 1. Отправляем аудиофайл в Whisper от OpenAI через ProxyAPI для транскрибации
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            files = {'file': ('voice.ogg', bytes(voice_bytes), 'audio/ogg')}
            data = {'model': 'whisper-1'}
            
            whisper_response = await client.post(
                WHISPER_URL,
                headers={'Authorization': f'Bearer {PROXY_API_KEY}'},
                files=files,
                data=data
            )
            
            if whisper_response.status_code == 200:
                transcribed_text = whisper_response.json().get('text', '')
                if not transcribed_text:
                    await update.message.reply_text("Мне не удалось разобрать слова в голосовом сообщении.")
                    return
                
                # Уведомляем пользователя, что мы расшифровали его голос
                logger.info(f"Распознан голос: {transcribed_text}")
            else:
                logger.error(f"Ошибка Whisper API: {whisper_response.status_code}")
                await update.message.reply_text("Не удалось распознать голосовое сообщение.")
                return
        except Exception as e:
            logger.error(f"Ошибка при обращении к Whisper: {e}")
            await update.message.reply_text("Произошла ошибка при обработке аудио.")
            return

    # 2. Отправляем распознанный текст в Grok 4.5
    payload = [{'role': 'user', 'content': f"(Пользователь наговорил голосом): {transcribed_text}"}]
    reply = await ask_grok(payload)
    
    # Добавляем к ответу текст расшифровки для удобства
    await update.message.reply_text(f"📝 *Ваш запрос:* _{transcribed_text}_\n\n🤖 *Раджу:* {reply}", parse_mode="Markdown")

async def main_async() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Регистрация обработчиков команд
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    
    # Регистрация разных типов входящего контента
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Ручная асинхронная инициализация компонентов для стабильности на Render
    await application.initialize()
    await application.start()

    if RENDER_EXTERNAL_URL:
        logger.info(f"Запуск вебхука на порту {PORT}")
        updater = application.updater
        if updater:
            await updater.start_webhook(
                listen="0.0.0.0",
                port=PORT,
                secret_token="A1b2C3d4E5f6G7h8",
                url_path=TELEGRAM_TOKEN,
                webhook_url=f"{RENDER_EXTERNAL_URL}/{TELEGRAM_TOKEN}"
            )
        while True:
            await asyncio.sleep(3600)
    else:
        logger.info("Запуск локального Polling")
        updater = application.updater
        if updater:
            await updater.start_polling()
            while True:
                await asyncio.sleep(3600)

def main() -> None:
    try:
        asyncio.run(main_async())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")

if __name__ == '__main__':
    main()
