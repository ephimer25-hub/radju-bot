import os
import logging
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Берем токены из Переменных Окружения (Environment Variables) на Render
# НИКОГДА не вставляйте токены прямо в код!
TELEGRAM_TOKEN = os.getenv("8804377859:AAHybYDorTb9c4j-o90D2tHYr_x2NNo0qaE")
PROXY_API_KEY = os.getenv("sk-w7178jSfKD6ttClL6jKlJ67BPKfJDmZL")

# URL вашего приложения на Render (например, https://onrender.com)
# Обязательно укажите его в настройках Render (Environment Variables)
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL") 
PORT = int(os.getenv("PORT", 8443))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Привет! Я Раджу, ваш уникальный ИИ-агент. Как я могу помочь?')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Я могу помочь вам с различными задачами. Просто напишите мне.')

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    
    # Отправляем пользователю статус, что ИИ "думает"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Корректный запрос к ProxyAPI (используем стандартный эндпоинт OpenAI-style)
    # Используем асинхронный httpx вместо синхронного requests, чтобы бот не зависал
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                'https://proxyapi.ru', # Актуальный URL ProxyAPI
                headers={
                    'Authorization': f'Bearer {PROXY_API_KEY}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'gpt-4o-mini', # Или любая другая модель, доступная в вашем кабинете ProxyAPI
                    'messages': [{'role': 'user', 'content': user_message}]
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                reply_message = result['choices'][0]['message']['content']
                await update.message.reply_text(reply_message)
            else:
                logger.error(f"Ошибка API: {response.status_code} - {response.text}")
                await update.message.reply_text('Извините, произошла ошибка при обращении к нейросети.')
                
        except Exception as e:
            logger.error(f"Ошибка при отправке запроса: {e}")
            await update.message.reply_text('Не удалось связаться с сервером ИИ.')

def main() -> None:
    # Создаем приложение бота
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Регистрируем обработчики команд и сообщений
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Логика деплоя: если есть URL от Render — запускаем Webhook, иначе — Polling (для тестов на ПК)
    if RENDER_EXTERNAL_URL:
        logger.info(f"Запуск в режиме Webhook на порту {PORT}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            secret_token="A1b2C3d4E5f6G7h8", # Защита вашего вебхука от спама
            url_path=TELEGRAM_TOKEN,
            webhook_url=f"{RENDER_EXTERNAL_URL}/{TELEGRAM_TOKEN}"
        )
    else:
        logger.info("Запуск в режиме Polling (Локально)")
        application.run_polling()

if __name__ == '__main__':
    main()
