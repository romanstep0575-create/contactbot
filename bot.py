import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
import aiohttp
from database import init_db, get_user, create_user, update_credits, add_search_history

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота
BOT_TOKEN = os.getenv('BOT_TOKEN')
DADATA_TOKEN = os.getenv('DADATA_API_KEY')
DADATA_SECRET = os.getenv('DADATA_SECRET_KEY')

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в переменных окружения!")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Состояния
class SearchStates(StatesGroup):
    waiting_for_query = State()

# Цены
PRICES = {
    '50': {'credits': 50, 'price': 499, 'label': '50 кредитов - 499₽'},
    '250': {'credits': 250, 'price': 1990, 'label': '250 кредитов - 1990₽'},
    '750': {'credits': 750, 'price': 4990, 'label': '750 кредитов - 4990₽'},
}

# ============================================
# ФУНКЦИЯ ПОИСКА В DADATA
# ============================================

async def search_company(query: str):
    """Поиск компании через DaData API"""
    if not DADATA_TOKEN:
        logger.error("DaData токен не настроен!")
        return None
    
    try:
        url = "https://suggestions.api.dadata.ru/suggestions/api/4_1/rs/suggest/party"
        headers = {
            "Authorization": f"Token {DADATA_TOKEN}",
            "Content-Type": "application/json"
        }
        data_req = {"query": query, "count": 1}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data_req) as response:
                if response.status == 200:
                    result = await response.json()
                    suggestions = result.get('suggestions', [])
                    
                    if suggestions:
                        company = suggestions[0]
                        data = company.get('data', {})
                        management = data.get('management', {})
                        state = data.get('state', {})
                        address_data = data.get('address', {})
                        name_data = data.get('name', {})
                        
                        emails = data.get('emails')
                        phones = data.get('phones')
                        
                        email = None
                        if emails and len(emails) > 0:
                            email = emails[0].get('value') if isinstance(emails[0], dict) else emails[0]
                        
                        phone = None
                        if phones and len(phones) > 0:
                            phone = phones[0].get('value') if isinstance(phones[0], dict) else phones[0]
                        
                        return {
                            'inn': data.get('inn'),
                            'ogrn': data.get('ogrn'),
                            'kpp': data.get('kpp'),
                            'full_name': name_data.get('full_with_opf'),
                            'short_name': name_data.get('short_with_opf'),
                            'director_name': management.get('name'),
                            'director_post': management.get('post') or 'Генеральный директор',
                            'address': address_data.get('value'),
                            'status': state.get('status'),
                            'registration_date': state.get('registration_date'),
                            'email': email,
                            'phone': phone,
                        }
                else:
                    logger.error(f"DaData API error: {response.status}")
    except Exception as e:
        logger.error(f"DaData Error: {e}")
    
    return None

# ============================================
# ОБРАБОТЧИКИ КОМАНД
# ============================================

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """Команда /start"""
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await create_user(user_id, message.from_user.username or "Anonymous", 10)
        credits = 10
        is_new = True
    else:
        credits = user['credits']
        is_new = False
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🔍 Найти компанию", callback_data="search"),
        InlineKeyboardButton("💳 Купить кредиты", callback_data="buy"),
        InlineKeyboardButton("📊 Мой баланс", callback_data="balance"),
        InlineKeyboardButton("ℹ️ Как работает", callback_data="help")
    )
    
    welcome_text = f"""
🇷🇺 <b>ContactFinder - Поиск компаний РФ</b>

Найду полные данные любой российской компании:

📋 <b>ЕГРЮЛ данные:</b>
• ИНН, ОГРН, КПП
• ФИО директора
• Юридический адрес
• Дата регистрации

📞 <b>Контакты:</b>
• Email компании
• Телефон компании

{'🎁 <b>Вам начислено 10 бесплатных кредитов!</b>' if is_new else f'💰 <b>Ваш баланс:</b> {credits} кредитов'}

<i>1 поиск = 1 кредит</i>
"""
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode='HTML')


@dp.callback_query_handler(lambda c: c.data == "help")
async def show_help(callback: types.CallbackQuery):
    """Помощь"""
    help_text = """
<b>📖 Как работает ContactFinder?</b>

1️⃣ Вы вводите название компании или ИНН
2️⃣ Мы ищем в официальной базе ЕГРЮЛ
3️⃣ Возвращаем полные данные

<b>Примеры запросов:</b>
• Яндекс
• ООО Рога и Копыта
• Сбербанк
• 7707083893 (ИНН)

<b>Что вы получите:</b>
✅ Полные реквизиты компании
✅ ФИО директора
✅ Email и телефон (если есть)
✅ Юридический адрес

<b>Источник:</b> DaData (ЕГРЮЛ)
"""
    await callback.message.answer(help_text, parse_mode='HTML')
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "search")
async def start_search(callback: types.CallbackQuery):
    """Начало поиска"""
    user_id = callback.from_user.id
    user = await get_user(user_id)
    
    if not user or user['credits'] < 1:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("💳 Купить кредиты", callback_data="buy"))
        await callback.message.answer(
            "❌ <b>Недостаточно кредитов!</b>\n\nПополните баланс.",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        await callback.answer()
        return
    
    await callback.message.answer(
        "🏢 <b>Введите название компании или ИНН:</b>\n\n"
        "<b>Примеры:</b>\n"
        "• Яндекс\n"
        "• ООО Технологии\n"
        "• 7707083893\n\n"
        "Я найду все данные из ЕГРЮЛ 🎯",
        parse_mode='HTML'
    )
    await SearchStates.waiting_for_query.set()
    await callback.answer()


@dp.message_handler(state=SearchStates.waiting_for_query)
async def process_search(message: types.Message, state: FSMContext):
    """Обработка поиска"""
    query = message.text.strip()
    user_id = message.from_user.id
    
    # Списываем кредит
    await update_credits(user_id, -1)
    
    # Показываем прогресс
    progress_msg = await message.answer(
        "🔍 <b>Ищу данные...</b>\n\n"
        "⏳ Проверяю базу ЕГРЮЛ\n\n"
        "<i>Подождите 5-10 секунд</i>",
        parse_mode='HTML'
    )
    
    # ПОИСК
    company = await search_company(query)
    
    if company:
        # НАЙДЕНО!
        response = f"""
✅ <b>ДАННЫЕ НАЙДЕНЫ</b>

━━━━━━━━━━━━━━━━━━━━
📋 <b>КОМПАНИЯ</b>
━━━━━━━━━━━━━━━━━━━━

<b>Название:</b>
{company.get('full_name', 'Н/Д')}

<b>ИНН:</b> <code>{company.get('inn', 'Н/Д')}</code>
<b>ОГРН:</b> <code>{company.get('ogrn', 'Н/Д')}</code>
<b>КПП:</b> <code>{company.get('kpp', 'Н/Д')}</code>

<b>Статус:</b> {company.get('status', 'Н/Д')}
<b>Дата регистрации:</b> {company.get('registration_date', 'Н/Д')}

<b>Адрес:</b>
{company.get('address', 'Н/Д')[:200]}...

━━━━━━━━━━━━━━━━━━━━
👤 <b>РУКОВОДИТЕЛЬ</b>
━━━━━━━━━━━━━━━━━━━━

<b>ФИО:</b> {company.get('director_name', 'Н/Д')}
<b>Должность:</b> {company.get('director_post', 'Н/Д')}
"""
        
        # Добавляем контакты если есть
        if company.get('email') or company.get('phone'):
            response += "\n━━━━━━━━━━━━━━━━━━━━\n"
            response += "📞 <b>КОНТАКТЫ</b>\n"
            response += "━━━━━━━━━━━━━━━━━━━━\n\n"
            
            if company.get('email'):
                response += f"📧 Email: <code>{company['email']}</code>\n"
            if company.get('phone'):
                response += f"📱 Телефон: <code>{company['phone']}</code>\n"
        
        response += "\n<i>📊 Источник: DaData (ЕГРЮЛ)</i>"
        
        await add_search_history(
            user_id,
            query,
            company.get('short_name', ''),
            company.get('email'),
            True
        )
        
        await progress_msg.edit_text(response, parse_mode='HTML')
        
    else:
        # НЕ НАЙДЕНО
        await add_search_history(user_id, query, '', None, False)
        
        await progress_msg.edit_text(
            f"❌ <b>Компания не найдена</b>\n\n"
            f"Запрос: <i>{query}</i>\n\n"
            f"💡 <b>Попробуйте:</b>\n"
            f"• Проверьте правильность написания\n"
            f"• Используйте полное название (ООО, АО)\n"
            f"• Введите ИНН компании\n\n"
            f"🔄 <b>Кредит НЕ списан</b>",
            parse_mode='HTML'
        )
        
        # Возвращаем кредит
        await update_credits(user_id, 1)
    
    # Сбрасываем состояние
    await state.finish()
    
    # Показываем баланс
    user = await get_user(user_id)
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("🔍 Еще поиск", callback_data="search"),
        InlineKeyboardButton("💳 Купить кредиты", callback_data="buy")
    )
    
    await message.answer(
        f"💰 <b>Осталось кредитов:</b> {user['credits']}",
        reply_markup=keyboard,
        parse_mode='HTML'
    )


@dp.callback_query_handler(lambda c: c.data == "balance")
async def show_balance(callback: types.CallbackQuery):
    """Баланс"""
    user_id = callback.from_user.id
    user = await get_user(user_id)
    
    success_rate = 0
    if user.get('total_searches', 0) > 0:
        success_rate = round((user.get('successful_searches', 0) / user['total_searches']) * 100)
    
    await callback.message.answer(
        f"📊 <b>ВАША СТАТИСТИКА</b>\n\n"
        f"💰 <b>Баланс:</b> {user['credits']} кредитов\n\n"
        f"📈 <b>Активность:</b>\n"
        f"├ Всего поисков: {user.get('total_searches', 0)}\n"
        f"├ Успешных: {user.get('successful_searches', 0)}\n"
        f"└ Процент успеха: {success_rate}%",
        parse_mode='HTML'
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "buy")
async def show_prices(callback: types.CallbackQuery):
    """Цены"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(PRICES['50']['label'], callback_data="buy_50"),
        InlineKeyboardButton(PRICES['250']['label'], callback_data="buy_250"),
        InlineKeyboardButton(PRICES['750']['label'], callback_data="buy_750")
    )
    
    await callback.message.answer(
        "💳 <b>ПАКЕТЫ КРЕДИТОВ</b>\n\n"
        "1 кредит = 1 поиск компании\n\n"
        "💎 При покупке от 250 кредитов - скидка 20%!\n\n"
        "Выберите пакет:",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("buy_"))
async def process_payment(callback: types.CallbackQuery):
    """Покупка"""
    package = callback.data.replace("buy_", "")
    admin_id = os.getenv('ADMIN_ID', 'yourusername')
    
    await callback.message.answer(
        f"💳 <b>ОПЛАТА</b>\n\n"
        f"Пакет: <b>{PRICES[package]['label']}</b>\n\n"
        f"<b>Для покупки напишите:</b>\n"
        f"@{admin_id}\n\n"
        f"<b>Укажите:</b>\n"
        f"• Выбранный пакет\n"
        f"• Ваш ID: <code>{callback.from_user.id}</code>\n\n"
        f"Кредиты будут начислены в течение 5 минут! ⚡",
        parse_mode='HTML'
    )
    await callback.answer()


# ============================================
# ЗАПУСК БОТА
# ============================================

async def on_startup(dp):
    """При запуске"""
    await init_db()
    logger.info("=" * 50)
    logger.info("🚀 Бот успешно запущен!")
    logger.info("=" * 50)


async def on_shutdown(dp):
    """При остановке"""
    logger.info("👋 Бот остановлен")
    await bot.close()


if __name__ == '__main__':
    from aiogram import executor
    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown, skip_updates=True)
