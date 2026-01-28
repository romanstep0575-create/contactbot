import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dadata import Dadata
from database import init_db, get_user, create_user, update_credits, add_search_history

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
DADATA_TOKEN = os.getenv('DADATA_API_KEY')
DADATA_SECRET = os.getenv('DADATA_SECRET_KEY')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
dadata = Dadata(DADATA_TOKEN, DADATA_SECRET) if DADATA_TOKEN else None

class SearchStates(StatesGroup):
    waiting_for_query = State()

PRICES = {
    '50': {'credits': 50, 'price': 499, 'label': '50 кредитов - 499₽'},
    '250': {'credits': 250, 'price': 1990, 'label': '250 кредитов - 1990₽'},
    '750': {'credits': 750, 'price': 4990, 'label': '750 кредитов - 4990₽'},
}

async def search_company(query: str):
    if not dadata:
        return None
    try:
        result = dadata.suggest("party", query, count=1)
        if result:
            company = result[0]
            data = company.get('data', {})
            management = data.get('management', {})
            state = data.get('state', {})
            address_data = data.get('address', {})
            name_data = data.get('name', {})
            emails = data.get('emails')
            phones = data.get('phones')
            
            email = emails[0].get('value') if emails and isinstance(emails[0], dict) else (emails[0] if emails else None)
            phone = phones[0].get('value') if phones and isinstance(phones[0], dict) else (phones[0] if phones else None)
            
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
    except Exception as e:
        logger.error(f"Error: {e}")
    return None

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await create_user(user_id, message.from_user.username or "Anonymous", 10)
        credits = 10
        is_new = True
    else:
        credits = user['credits']
        is_new = False
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Найти компанию", callback_data="search")],
        [InlineKeyboardButton(text="💳 Купить кредиты", callback_data="buy")],
        [InlineKeyboardButton(text="📊 Мой баланс", callback_data="balance")]
    ])
    
    text = f"🇷🇺 <b>ContactFinder</b>\n\nНайду данные любой российской компании из ЕГРЮЛ.\n\n{'🎁 Вам начислено 10 бесплатных кредитов!' if is_new else f'💰 Баланс: {credits} кредитов'}"
    await message.answer(text, reply_markup=keyboard, parse_mode='HTML')

@dp.callback_query(F.data == "search")
async def start_search(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    if not user or user['credits'] < 1:
        await callback.message.answer("❌ Недостаточно кредитов!")
        await callback.answer()
        return
    
    await callback.message.answer("🏢 Введите название компании или ИНН:\n\nПример: Яндекс или 7707083893")
    await state.set_state(SearchStates.waiting_for_query)
    await callback.answer()

@dp.message(SearchStates.waiting_for_query)
async def process_search(message: Message, state: FSMContext):
    query = message.text.strip()
    user_id = message.from_user.id
    
    await update_credits(user_id, -1)
    progress = await message.answer("🔍 Ищу данные...")
    
    company = await search_company(query)
    
    if company:
        response = f"✅ <b>НАЙДЕНО</b>\n\n<b>Компания:</b>\n{company.get('full_name', 'Н/Д')}\n\n<b>ИНН:</b> <code>{company.get('inn')}</code>\n<b>ОГРН:</b> <code>{company.get('ogrn')}</code>\n\n<b>Директор:</b> {company.get('director_name', 'Н/Д')}\n<b>Должность:</b> {company.get('director_post')}\n\n<b>Адрес:</b>\n{company.get('address', 'Н/Д')[:150]}..."
        
        if company.get('email') or company.get('phone'):
            response += f"\n\n📞 <b>Контакты:</b>\n"
            if company.get('email'):
                response += f"Email: <code>{company['email']}</code>\n"
            if company.get('phone'):
                response += f"Телефон: <code>{company['phone']}</code>"
        
        await add_search_history(user_id, query, company.get('short_name', ''), company.get('email'), True)
        await progress.edit_text(response, parse_mode='HTML')
    else:
        await add_search_history(user_id, query, '', None, False)
        await progress.edit_text(f"❌ Не найдено: {query}\n\n🔄 Кредит НЕ списан")
        await update_credits(user_id, 1)
    
    await state.clear()
    user = await get_user(user_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔍 Еще поиск", callback_data="search")]])
    await message.answer(f"💰 Осталось: {user['credits']} кредитов", reply_markup=keyboard)

@dp.callback_query(F.data == "balance")
async def show_balance(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    await callback.message.answer(f"💰 Баланс: {user['credits']} кредитов\n📊 Поисков: {user.get('total_searches', 0)}")
    await callback.answer()

@dp.callback_query(F.data == "buy")
async def show_prices(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=PRICES['50']['label'], callback_data="buy_50")],
        [InlineKeyboardButton(text=PRICES['250']['label'], callback_data="buy_250")]
    ])
    await callback.message.answer("💳 Выберите пакет:", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def process_payment(callback: CallbackQuery):
    await callback.message.answer(f"Для покупки напишите админу\nВаш ID: <code>{callback.from_user.id}</code>", parse_mode='HTML')
    await callback.answer()

async def main():
    logger.info("🚀 Бот запускается...")
    await init_db()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
