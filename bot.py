import os
import logging
import telebot
from telebot import types
import sqlite3
import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
DADATA_API_KEY = os.getenv('DADATA_API_KEY')
DADATA_SECRET_KEY = os.getenv('DADATA_SECRET_KEY')

bot = telebot.TeleBot(BOT_TOKEN)
DB_PATH = 'contacts.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            credits INTEGER DEFAULT 0,
            total_searches INTEGER DEFAULT 0,
            successful_searches INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            query TEXT,
            company TEXT,
            email TEXT,
            found BOOLEAN,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("Database initialized")

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {'user_id': row[0], 'username': row[1], 'credits': row[2], 'total_searches': row[3], 'successful_searches': row[4]}
    return None

def create_user(user_id, username, credits=10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO users (user_id, username, credits) VALUES (?, ?, ?)', (user_id, username, credits))
    conn.commit()
    conn.close()

def update_credits(user_id, amount):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET credits = credits + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def add_search_history(user_id, query, company, email, found):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO search_history (user_id, query, company, email, found) VALUES (?, ?, ?, ?, ?)', (user_id, query, company, email, found))
    if found:
        cursor.execute('UPDATE users SET total_searches = total_searches + 1, successful_searches = successful_searches + 1 WHERE user_id = ?', (user_id,))
    else:
        cursor.execute('UPDATE users SET total_searches = total_searches + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def search_company_dadata(query):
    url = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party"
    headers = {"Authorization": f"Token {DADATA_API_KEY}", "Content-Type": "application/json"}
    data = {"query": query, "count": 5}
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            return response.json().get('suggestions', [])
        return []
    except Exception as e:
        logger.error(f"DaData error: {e}")
        return []

def search_phone_dadata(phone):
    """Поиск информации о телефоне через DaData Clean API"""
    url = "https://cleaner.dadata.ru/api/v1/clean/phone"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Token {DADATA_API_KEY}",
        "X-Secret": DADATA_SECRET_KEY
    }
    data = [phone]
    
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            result = response.json()
            if result and len(result) > 0:
                return result[0]
        return None
    except Exception as e:
        logger.error(f"DaData phone search error: {e}")
        return None

def format_company_info(suggestion):
    data = suggestion.get('data', {})
    name = data.get('name', {}).get('full_with_opf', 'Не указано')
    inn = data.get('inn', 'Не указано')
    kpp = data.get('kpp', 'Не указано')
    ogrn = data.get('ogrn', 'Не указано')
    address = data.get('address', {}).get('value', 'Не указано')
    management = data.get('management', {})
    ceo = management.get('name', 'Не указано') if management else 'Не указано'
    emails = data.get('emails', [])
    phones = data.get('phones', [])
    email_str = ', '.join([e.get('value', '') for e in emails]) if emails else 'Не найдено'
    phone_str = ', '.join([p.get('value', '') for p in phones]) if phones else 'Не найдено'
    result = f"🏢 <b>{name}</b>\n\n📋 <b>Реквизиты:</b>\n• ИНН: {inn}\n• КПП: {kpp}\n• ОГРН: {ogrn}\n\n📍 <b>Адрес:</b>\n{address}\n\n👤 <b>Руководитель:</b>\n{ceo}\n\n📧 <b>Email:</b> {email_str}\n📞 <b>Телефон:</b> {phone_str}"
    return result, bool(emails)

def format_phone_info(phone_data):
    """Форматирует информацию о телефоне"""
    if not phone_data:
        return "❌ Информация не найдена", False
    
    phone = phone_data.get('phone', 'Не указан')
    country = phone_data.get('country', 'Не указана')
    city = phone_data.get('city', 'Не указан')
    provider = phone_data.get('provider', 'Не указан')
    phone_type = phone_data.get('type', 'Не указан')
    region = phone_data.get('region', 'Не указан')
    timezone = phone_data.get('timezone', 'Не указан')
    
    result = f"📞 <b>Телефон:</b> {phone}\n\n"
    result += f"🌍 <b>Страна:</b> {country}\n"
    result += f"🏙 <b>Регион:</b> {region}\n"
    result += f"📍 <b>Город:</b> {city}\n"
    result += f"📡 <b>Оператор:</b> {provider}\n"
    result += f"📱 <b>Тип:</b> {phone_type}\n"
    result += f"🕐 <b>Часовой пояс:</b> {timezone}\n"
    
    return result, True

def get_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("🔍 Поиск контактов"))
    keyboard.add(types.KeyboardButton("📞 Поиск по телефону"))
    keyboard.add(types.KeyboardButton("💰 Баланс"), types.KeyboardButton("📊 Статистика"))
    keyboard.add(types.KeyboardButton("ℹ️ Помощь"))
    return keyboard

user_states = {}

@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    user = get_user(user_id)
    if not user:
        create_user(user_id, username, credits=10)
        text = f"👋 Привет, {username}!\n\nДобро пожаловать в бота для поиска контактов компаний!\n\n🎁 Вам начислено 10 бесплатных кредитов для тестирования.\n\nИспользуйте кнопки меню для навигации."
    else:
        text = f"С возвращением, {username}! 👋"
    bot.send_message(message.chat.id, text, reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "💰 Баланс")
def show_balance(message):
    user = get_user(message.from_user.id)
    if user:
        text = f"💰 <b>Ваш баланс:</b> {user['credits']} кредитов"
    else:
        text = "Ошибка: пользователь не найден. Используйте /start"
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text == "📊 Статистика")
def show_stats(message):
    user = get_user(message.from_user.id)
    if user:
        text = f"📊 <b>Ваша статистика:</b>\n\n• Всего поисков: {user['total_searches']}\n• Успешных: {user['successful_searches']}\n• Кредитов осталось: {user['credits']}"
    else:
        text = "Ошибка: пользователь не найден. Используйте /start"
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text == "ℹ️ Помощь")
@bot.message_handler(commands=['help'])
def show_help(message):
    text = "ℹ️ <b>Помощь по использованию бота</b>\n\n<b>Как искать контакты:</b>\n1. Нажмите 'Поиск контактов'\n2. Введите название компании или ИНН\n3. Получите результаты с контактами\n\n<b>Стоимость:</b>\n1 поиск = 1 кредит"
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text == "🔍 Поиск контактов")
def start_search(message):
    user = get_user(message.from_user.id)
    if not user:
        bot.send_message(message.chat.id, "Используйте /start для начала работы")
        return
    if user['credits'] <= 0:
        bot.send_message(message.chat.id, "❌ У вас закончились кредиты!")
        return
    user_states[message.from_user.id] = 'waiting_for_query'
    bot.send_message(message.chat.id, "🔍 Введите название компании или ИНН для поиска:", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda message: message.text == "📞 Поиск по телефону")
def start_phone_search(message):
    user = get_user(message.from_user.id)
    if not user:
        bot.send_message(message.chat.id, "Используйте /start для начала работы")
        return
    if user['credits'] <= 0:
        bot.send_message(message.chat.id, "❌ У вас закончились кредиты!")
        return
    user_states[message.from_user.id] = 'waiting_for_phone'
    bot.send_message(message.chat.id, "📞 Введите номер телефона для поиска:\n\nПример: +79161234567 или 8 916 123-45-67", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == 'waiting_for_query')
def process_search(message):
    query = message.text.strip()
    bot.send_message(message.chat.id, "⏳ Ищу информацию...")
    suggestions = search_company_dadata(query)
    if not suggestions:
        add_search_history(message.from_user.id, query, "Не найдено", "", False)
        bot.send_message(message.chat.id, "❌ По вашему запросу ничего не найдено.", reply_markup=get_main_keyboard())
        user_states.pop(message.from_user.id, None)
        return
    update_credits(message.from_user.id, -1)
    for i, suggestion in enumerate(suggestions[:3], 1):
        company_info, has_email = format_company_info(suggestion)
        bot.send_message(message.chat.id, f"<b>Результат {i}:</b>\n{company_info}", parse_mode='HTML')
        if i == 1:
            company_name = suggestion.get('data', {}).get('name', {}).get('short_with_opf', query)
            emails = suggestion.get('data', {}).get('emails', [])
            email = emails[0].get('value', '') if emails else ''
            add_search_history(message.from_user.id, query, company_name, email, has_email)
    user = get_user(message.from_user.id)
    bot.send_message(message.chat.id, f"✅ Поиск завершён!\n💰 Осталось кредитов: {user['credits']}", reply_markup=get_main_keyboard())
    user_states.pop(message.from_user.id, None)

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == 'waiting_for_phone')
def process_phone_search(message):
    phone = message.text.strip()
    bot.send_message(message.chat.id, "⏳ Ищу информацию о телефоне...")
    
    phone_data = search_phone_dadata(phone)
    
    if not phone_data or phone_data.get('qc') != 0:
        add_search_history(message.from_user.id, phone, "Телефон", "", False)
        bot.send_message(message.chat.id, "❌ Не удалось найти информацию по этому номеру.", reply_markup=get_main_keyboard())
        user_states.pop(message.from_user.id, None)
        return
    
    update_credits(message.from_user.id, -1)
    
    phone_info, found = format_phone_info(phone_data)
    bot.send_message(message.chat.id, phone_info, parse_mode='HTML')
    
    add_search_history(message.from_user.id, phone, "Телефон", "", found)
    
    user = get_user(message.from_user.id)
    bot.send_message(message.chat.id, f"✅ Поиск завершён!\n💰 Осталось кредитов: {user['credits']}", reply_markup=get_main_keyboard())
    user_states.pop(message.from_user.id, None)

if __name__ == '__main__':
    init_db()
    logger.info("Бот запущен!")
    bot.polling(none_stop=True)