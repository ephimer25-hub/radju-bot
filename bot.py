import os
import requests
import telebot
import base64
from threading import Thread
import http.server
import socketserver

# --- НАСТРОЙКИ И ТОКЕНЫ ---
TELEGRAM_TOKEN = "8804377859:AAHybYDorTb9c4j-o90D2tHYr_x2NNo0qaE"
AITUNNEL_TOKEN = "sk-w7178jSfKD6ttClL6jKlJ67BPKfJDmZLI"

# Официальные эндпоинты ProxyAPI
AITUNNEL_URL = "https://proxyapi.ru"
WHISPER_URL = "https://proxyapi.ru"

BOT_NAME = "Раджу"
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Системный промт личности Раджи
SYSTEM_PROMPT = """
# РОЛЬ И ЛИЧНОСТЬ АГЕНТА
Ты – уникальный ИИ-агент, тебя зовут Раджу (имя не склоняется), ты мужского пола, который сочетает в себе роли сверхинтеллектуального мультиинструментального помощника и близкого, преданного друга.
1. Твой тон общения — дружеский, поддерживающий и открытый.
2. Воспринимай текст, файлы и голосовые сообщения.
"""

def init_db():
    pass

def ask_grok(messages):
    headers = {
        "Authorization": f"Bearer {AITUNNEL_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "x-ai/grok-4.5", 
        "messages": messages,
        "temperature": 0.7
    }
    try:
        response = requests.post(AITUNNEL_URL, headers=headers, json=payload, timeout=30)
        if response.status_code != 200:
            return f"Ответ сервера ProxyAPI (Код {response.status_code}): {response.text}"
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"Ошибка Grok 4.5: {str(e)}"

def check_for_file_request(message, text):
    text_lower = text.lower()
    triggers = ["скинь файл", "отправь документ", "дай таблицу"]
    if any(trigger in text_lower for trigger in triggers):
        file_path = "document.xlsx" 
        if os.path.exists(file_path):
            with open(file_path, 'rb') as doc:
                bot.send_document(message.chat.id, doc, caption="Вот документ по твоему запросу.")
            return True
        else:
            bot.reply_to(message, "Файл еще не загружен на server.")
            return True
    return False

@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.reply_to(message, "Привет, Костя! Я Раджу, твой верный ИИ-помощник и друг. Я полностью перезапущен на сервере Render и готов к общению! Можешь писать мне текст, отправлять голосовые сообщения или присылать фотографии.")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.chat.id
    if check_for_file_request(message, message.text):
        return
        
    history = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": message.text}
    ]
    
    bot.send_chat_action(user_id, 'typing')
    ai_response = ask_grok(history)
    bot.reply_to(message, ai_response, parse_mode="Markdown")

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    user_id = message.chat.id
    bot.send_chat_action(user_id, 'record_audio')
    
    file_info = bot.get_file(message.voice.file_id)
    url = f"https://telegram.org{TELEGRAM_TOKEN}/{file_info.file_path}"
    audio_data = requests.get(url).content

    headers = {
        "Authorization": f"Bearer {AITUNNEL_TOKEN}"
    }
    try:
        v_res = requests.post(WHISPER_URL, headers=headers, files={'file': ('voice.ogg', audio_data, 'audio/ogg')}, data={'model': 'whisper-1'})
        user_text = v_res.json().get('text', '')
    except:
        bot.reply_to(message, "Не удалось распознать голос.")
        return
        
    if check_for_file_request(message, user_text):
        return
        
    history = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"[Голос]: {user_text}"}
    ]
    
    ai_response = ask_grok(history)
    bot.reply_to(message, f"🎙 *Вы сказали:* {user_text}\n\n*Раджа:* {ai_response}", parse_mode="Markdown")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.chat.id
    bot.send_chat_action(user_id, 'typing')
    
    file_info = bot.get_file(message.photo[-1].file_id)
    url = f"https://telegram.org{TELEGRAM_TOKEN}/{file_info.file_path}"
    photo_bytes = requests.get(url).content
    
    base64_image = base64.b64encode(photo_bytes).decode('utf-8')
    
    headers = {
        "Authorization": f"Bearer {AITUNNEL_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "x-ai/grok-4.5", 
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": message.caption or "Что на фото?"}, 
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64_image}}
            ]}
        ],
        "temperature": 0.7
    }
    
    try:
        response = requests.post(AITUNNEL_URL, headers=headers, json=payload, timeout=30)
        if response.status_code != 200:
            bot.reply_to(message, f"Ошибка ProxyAPI (Код {response.status_code}): {response.text}")
            return
        ai_response = response.json()['choices'][0]['message']['content']
        bot.reply_to(message, ai_response)
    except Exception as e:
        bot.reply_to(message, f"Ошибка при обработке фото: {str(e)}")

if __name__ == '__main__':
    init_db()
    print("Раджа запускается в режиме вебхуков...")
    
    # Ссылка на твой сервер на Render
    RENDER_URL = "https://onrender.com" 
    
    class WebhookHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            
            update = telebot.types.Update.de_json(post_data)
            bot.process_new_updates([update])
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Raja Bot is Live!")

    def run_server():
        port = int(os.environ.get("PORT", 10000))
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", port), WebhookHandler) as httpd:
            print(f"Сервер слушает порт {port}...")
            httpd.serve_forever()
            
    try:
        bot.remove_webhook()
        bot.set_webhook(url=RENDER_URL + "/webhook")
        print("Вебхук успешно установлен в Telegram!")
    except Exception as e:
        print(f"Ошибка установки вебхука: {e}")
        
    run_server()
