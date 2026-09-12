import os
import sqlite3
import requests
import telebot

# --- НАСТРОЙКИ И ТОКЕНЫ ---
TELEGRAM_TOKEN = "8804377859:AAF6XGYd_dSXgVOqAfChIvN3viXW93f0mYE"
AITUNNEL_TOKEN = "sk-aitunnel-051whwYPhpaEB38kc18DownfqjPw5fW1"

# Прямые рабочие эндпоинты без всяких прокси-шлюзов
AITUNNEL_URL = "https://aitunnel.ru" 
WHISPER_URL = "https://aitunnel.ru"

BOT_NAME = "Раджа"
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
        "Authorization": f"Bearer {AITUNNEL_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "grok-4.5", 
        "messages": messages,
        "temperature": 0.7
    }
    try:
        response = requests.post(AITUNNEL_URL, headers=headers, json=payload, timeout=30)
        return response.json()['choices']['message']['content']
    except Exception as e:
        return f"Ошибка Grok 4.5: {str(e)}"

@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.reply_to(message, "Привет! Я Раджа. Твой верный друг на базе Grok 4.5. Я полностью готов к работе!")

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
            bot.reply_to(message, "Файл еще не загружен на сервер.")
            return True
    return False

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
    file_url = f"https://telegram.org{TELEGRAM_TOKEN}/{file_info.file_path}"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [{"type": "text", "text": message.caption or "Что на фото?"}, {"type": "image_url", "image_url": {"url": file_url}}]}
    ]
    ai_response = ask_grok(messages)
    bot.reply_to(message, ai_response)

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

if __name__ == '__main__':
    init_db()
    print("Раджа запущен...")
    bot.infinity_polling()

