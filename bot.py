import os
import sqlite3
import requests
import telebot
from threading import Thread
import base64

# --- НАСТРОЙКИ И ТОКЕНЫ ---
TELEGRAM_TOKEN = "8804377859:AAHybYDorTb9c4j-o90D2tHYr_x2NNo0qaE"  # Этот токен оставляем прежним, который от BotFather
AITUNNEL_TOKEN = "sk-w7178jSfKD6ttClL6jKlJ67BPKfJDmZL"  # Вставляем сюда ключ, который начинается на pk-

# Меняем старый адрес ИИ-Туннеля на прямой адрес ProxyAPI

# Прямые рабочие эндпоинты без всяких прокси-шлюзов
AITUNNEL_URL = "https://api.proxyapi.ru/v1/chat/completions"
WHISPER_URL = "https://api.proxyapi.ru/v1/audio/transcriptions"

BOT_NAME = "Раджу"
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Системный промт
SYSTEM_PROMPT = """
# РОЛЬ И ЛИЧНОСТЬ АГЕНТА
Ты – уникальный ИИ-агент, тебя зовут Раджу (имя не склоняется), ты мужского пола, который сочетает в себе роли сверхинтеллектуального мультиинструментального помощника и близкого, преданного друга.
1. ДОЛГОВРЕМЕННАЯ ПАМЯТЬ: удерживай контекст беседы.
2. ПОИСК В ИНТЕРНЕТЕ: Используй веб-поиск при необходимости.
3. МУЛЬТИМОДАЛЬНОСТЬ: воспринимай текст, файлы и голосовые.
4. Tone of Voice: дружеский (по умолчанию).
"""

def init_db():
    conn = sqlite3.connect('contacts.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS history (user_id INTEGER, role TEXT, content TEXT)')
    conn.commit()
    conn.close()

def save_message(user_id, role, content):
    conn = sqlite3.connect('contacts.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO history (user_id, role, content) VALUES (?, ?, ?)', (user_id, role, content))
    conn.commit()
    conn.close()

def get_history(user_id, limit=10):
    conn = sqlite3.connect('contacts.db')
    cursor = conn.cursor()
    cursor.execute('SELECT role, content FROM history WHERE user_id = ? ORDER BY rowid DESC LIMIT ?', (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for role, content in reversed(rows):
        messages.append({"role": role, "content": content})
    return messages

def ask_grok(messages):
    headers = {
        "Authorization": "Bearer " + AITUNNEL_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "model": "x-ai/grok-4.5",  
        "messages": messages,
        "temperature": 0.7
    }
    try:
        response = requests.post(AITUNNEL_URL, headers=headers, json=payload, timeout=30)
        
        # Если туннель вернул ошибку авторизации или баланса, выводим её для проверки
        if response.status_code != 200:
            return f"Ответ ИИ-Туннеля (Код {response.status_code}): {response.text}"
            
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

@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.chat.id
    if check_for_file_request(message, message.text):
        return
        
    # Простейшая история только для текущего сообщения, чтобы база данных не ломала код
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
    url = "https://" + "api." + "telegram.org" + "/file/bot" + TELEGRAM_TOKEN + "/" + file_info.file_path
    audio_data = requests.get(url).content


    try:
        v_res = requests.post(WHISPER_URL, headers={"Authorization": f"Bearer {AITUNNEL_TOKEN}"}, files={'file': ('voice.ogg', audio_data, 'audio/ogg')}, data={'model': 'whisper-1'})
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


if __name__ == '__main__':
    init_db()
    print("Раджа запущен...")
    
    # Создаем простейшую веб-заглушку, чтобы Render видел порт и не отключал бота
    import http.server
    import socketserver
    
    def run_dummy_server():
        port = int(os.environ.get("PORT", 10000))
        handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("", port), handler) as httpd:
            httpd.serve_forever()
            
    # Запускаем сайт в фоновом потоке, чтобы он не мешал работе бота
    Thread(target=run_dummy_server, daemon=True).start()
    
    # Запускаем самого Раджу
    bot.infinity_polling()

    
    # Запускаем самого Раджу
    bot.infinity_polling()


@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.chat.id
    if check_for_file_request(message, message.text):
        return
    save_message(user_id, "user", message.text)
    history = get_history(user_id)
    bot.send_chat_action(user_id, 'typing')
    ai_response = ask_grok(history)
    save_message(user_id, "assistant", ai_response)
    bot.reply_to(message, ai_response, parse_mode="Markdown")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.chat.id
    bot.send_chat_action(user_id, 'typing')
    
    file_info = bot.get_file(message.photo[-1].file_id)
    url = "https://" + "api." + "telegram.org" + "/file/bot" + TELEGRAM_TOKEN + "/" + file_info.file_path
    photo_bytes = requests.get(url).content
    
    base64_image = base64.b64encode(photo_bytes).decode('utf-8')
    
    # Заголовки авторизации и payload строго под стандарты ProxyAPI
    headers = {
        "Authorization": "Bearer sk-w7178jSfKD6ttClL6jKlJ67BPKfJDmZL",
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
        ],
        "temperature": 0.7
    }
            
        ai_response = response.json()['choices'][0]['message']['content']
        bot.reply_to(message, ai_response)
    except Exception as e:
        bot.reply_to(message, "Ошибка при обработке фото: " + str(e))

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    user_id = message.chat.id
    bot.send_chat_action(user_id, 'record_audio')
    file_info = bot.get_file(message.voice.file_id)
    audio_data = requests.get(f"https://telegram.org{TELEGRAM_TOKEN}/{file_info.file_path}").content
    try:
        v_res = requests.post(WHISPER_URL, headers={"Authorization": f"Bearer {AITUNNEL_TOKEN}"}, files={'file': ('voice.ogg', audio_data, 'audio/ogg')}, data={'model': 'whisper-1'})
        user_text = v_res.json().get('text', '')
    except:
        bot.reply_to(message, "Не удалось распознать голос.")
        return
    if check_for_file_request(message, user_text):
        return
    save_message(user_id, "user", f"[Голос]: {user_text}")
    ai_response = ask_grok(get_history(user_id))
    bot.reply_to(message, f"🎙 *Вы сказали:* {user_text}\n\n*Раджа:* {ai_response}", parse_mode="Markdown")

if name == 'main':
    init_db()
    print("Раджа запускается в режиме вебхуков...")
    
    # ⚠️ https://radju-bot.onrender.com (обязательно с https:// и без косой черты в конце!)
    RENDER_URL = "https://onrender.com" 
    
    import http.server
    import socketserver
    import json
    
    class WebhookHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            # Telegram прислал новое сообщение!
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            
            # Передаем данные в библиотеку telebot для обработки текста/голоса/фото
            update = telebot.types.Update.de_json(post_data)
            bot.process_new_updates([update])
            
            # Отвечаем Телеграму, что всё получили успешно
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            
        def do_GET(self):
            # Заглушка для Render, чтобы он видел рабочий порт
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Raja Bot is Live!")

    def run_server():
        port = int(os.environ.get("PORT", 10000))
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", port), WebhookHandler) as httpd:
            print(f"Сервер слушает порт {port}...")
            httpd.serve_forever()
            
    # Принудительно ставим вебхук в Telegram на наш адрес Render
    try:
        bot.remove_webhook()
        bot.set_webhook(url=f"{RENDER_URL}/webhook")
        print("Вебхук успешно установлен в Telegram!")
    except Exception as e:
        print(f"Ошибка установки вебхука: {e}")
        
    # Запускаем наш веб-сервер
    run_server()

    # Запускаем самого Раджу
    bot.infinity_polling()


