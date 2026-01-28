import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from database import init_db, get_user, create_user, update_credits, add_search_history

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
DADATA_TOKEN = os.getenv('DADATA_API_KEY')
DADATA_SECRET = os.getenv('DADATA_SECRET_KEY')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
# DaData будет работать через HTTP запросы
class SearchStates(StatesGroup):
    waiting_for_query = State()

PRICES = {
    '50': {'credits': 50, 'price': 499, 'label': '50 кредитов - 499₽'},
    '250': {'credits': 250, 'price': 1990, 'label': '250 кредитов - 1990₽'},
    '750': {'credits': 750, 'price': 4990, 'label': '750 кредитов - 4990₽'},
}

async def search_company(query: str):
    """Поиск через DaData API напрямую"""
    if not DADATA_TOKEN:
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
    except Exception as e:
        logger.error(f"DaData Error: {e}")
    
    return None
