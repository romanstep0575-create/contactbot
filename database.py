import aiosqlite
import logging

logger = logging.getLogger(__name__)

DB_PATH = 'contacts.db'

async def init_db():
    """Инициализация базы данных"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                credits INTEGER DEFAULT 0,
                total_searches INTEGER DEFAULT 0,
                successful_searches INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await db.execute('''
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
        
        await db.commit()
        logger.info("✅ Database initialized")

async def get_user(user_id: int):
    """Получить пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT * FROM users WHERE user_id = ?', 
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def create_user(user_id: int, username: str, credits: int = 10):
    """Создать пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO users (user_id, username, credits) VALUES (?, ?, ?)',
            (user_id, username, credits)
        )
        await db.commit()
        logger.info(f"✅ User {user_id} created with {credits} credits")

async def update_credits(user_id: int, amount: int):
    """Обновить кредиты"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE users SET credits = credits + ? WHERE user_id = ?',
            (amount, user_id)
        )
        await db.commit()

async def add_search_history(user_id: int, query: str, company: str, 
                            email: str, found: bool):
    """Добавить в историю поисков"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''INSERT INTO search_history 
               (user_id, query, company, email, found) 
               VALUES (?, ?, ?, ?, ?)''',
            (user_id, query, company, email, found)
        )
        
        if found:
            await db.execute(
                '''UPDATE users 
                   SET total_searches = total_searches + 1,
                       successful_searches = successful_searches + 1
                   WHERE user_id = ?''',
                (user_id,)
            )
        else:
            await db.execute(
                'UPDATE users SET total_searches = total_searches + 1 WHERE user_id = ?',
                (user_id,)
            )
        
        await db.commit()
