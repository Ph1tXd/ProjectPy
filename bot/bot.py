from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.router import Router
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import psycopg2
import logging
import os

logging.basicConfig(level=logging.INFO)

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'bruno'),
    'user': os.getenv('DB_USER', 'bruno'),
    "password": os.getenv("DB_PASSWORD", "1234"),
    'host': os.getenv('DB_HOST', 'localhost'),
    "port": os.getenv('DB_PORT', 5432)
}

BOT_TOKEN = os.getenv('BOT_TOKEN')

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
router = Router()
dp = Dispatcher(storage=storage)
dp.include_router(router)

user_favorites = {}

def fetch_all_authors():
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT name FROM authors ORDER BY name;")
                return [row[0] for row in cursor.fetchall()]
    except psycopg2.Error as e:
        logging.error(f"Ошибка подключения к базе данных: {e}")
        return []

def fetch_matching_authors(search_query):
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT name FROM authors 
                    WHERE name ILIKE %s;
                """, (f"%{search_query}%",))
                return [row[0] for row in cursor.fetchall()]
    except psycopg2.Error as e:
        logging.error(f"Ошибка подключения к базе данных: {e}")
        return []

def fetch_author_info(author_name):
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT name, birth, bio 
                    FROM authors 
                    WHERE name = %s;
                """, (author_name,))
                result = cursor.fetchone()
                if result:
                    full_name, birth, bio = result
                    cursor.execute("""
                        SELECT text FROM quotes 
                        INNER JOIN authors ON quotes.author_id = authors.id 
                        WHERE authors.name = %s LIMIT 1;
                    """, (full_name,))
                    quote_result = cursor.fetchone()
                    quote = quote_result[0] if quote_result else "Цитат не найдено."
                    return full_name, birth, bio, quote
                else:
                    return None, None, None, None
    except psycopg2.Error as e:
        logging.error(f"Ошибка подключения к базе данных: {e}")
        return None, None, None, None

main_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Избранное")], [KeyboardButton(text="Показать авторов")]],
    resize_keyboard=True
)

@router.message(Command(commands=["start"]))
async def start_command(message: types.Message):
    authors = fetch_all_authors()
    if authors:
        response = "Список доступных авторов:\n"
        response += "\n".join(authors)
        response += "\n\nПожалуйста, напишите имя или фамилию автора из списка."
    else:
        response = "Не удалось загрузить список авторов. Проверьте подключение к базе данных."
    await message.answer(response, reply_markup=main_menu)

@router.message(lambda msg: msg.text == "Показать авторов")
async def show_all_authors(message: types.Message):
    authors = fetch_all_authors()
    if authors:
        response = "Список доступных авторов:\n"
        response += "\n".join(authors)
        response += "\n\nПожалуйста, напишите имя или фамилию автора из списка."
    else:
        response = "Не удалось загрузить список авторов. Проверьте подключение к базе данных."
    await message.answer(response)

@router.message(lambda msg: msg.text and msg.text not in ["Избранное", "Показать авторов"])
async def search_author(message: types.Message):
    search_query = message.text.strip()
    matching_authors = fetch_matching_authors(search_query)

    if len(matching_authors) > 1:
        response = "Найдено несколько авторов с похожим именем:\n"
        response += "\n".join(matching_authors)
        response += "\n\nПожалуйста, напишите полное имя автора из списка."
        await message.answer(response)
    elif len(matching_authors) == 1:
        full_name, birth, bio, quote = fetch_author_info(matching_authors[0])
        if full_name and bio:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Добавить в избранное", callback_data=f"add_fav_{full_name}")]
            ])
            response = (
                f"Автор: {full_name}\n\n"
                f"Дата и место рождения: {birth if birth else 'Неизвестно'}\n\n"
                f"Биография: {bio}\n\n"
                f"Цитата: {quote}"
            )
            await message.answer(response, reply_markup=keyboard)
        else:
            await message.answer("Информация об авторе не найдена.")
    else:
        await message.answer("Автор не найден. Попробуйте снова.")

@router.callback_query(lambda callback: callback.data.startswith("add_fav_"))
async def add_to_favorites(callback_query: types.CallbackQuery):
    author_name = callback_query.data.split("_")[2]
    user_id = callback_query.from_user.id

    if user_id not in user_favorites:
        user_favorites[user_id] = []
    if author_name not in user_favorites[user_id]:
        user_favorites[user_id].append(author_name)
        await callback_query.message.answer(f"Автор {author_name} добавлен в избранное.")
    else:
        await callback_query.message.answer(f"Автор {author_name} уже в избранном.")

@router.message(lambda msg: msg.text == "Избранное")
async def show_favorites(message: types.Message):
    user_id = message.from_user.id
    if user_id in user_favorites and user_favorites[user_id]:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=author, callback_data=f"fav_{author}")]
                for author in user_favorites[user_id]
            ]
        )
        await message.answer("Ваши избранные авторы:", reply_markup=keyboard)
    else:
        await message.answer("У вас нет избранных авторов.")

@router.callback_query(lambda callback: callback.data.startswith("fav_"))
async def show_favorite_author(callback_query: types.CallbackQuery):
    author_name = callback_query.data.split("_")[1]
    full_name, birth, bio, quote = fetch_author_info(author_name)

    if full_name and bio:
        response = (
            f"Автор: {full_name}\n"
            f"Дата и место рождения: {birth if birth else 'Неизвестно'}\n\n"
            f"Биография: {bio}\n\n"
            f"Цитата: {quote}"
        )
        await callback_query.message.answer(response)
    else:
        await callback_query.message.answer("Информация об авторе не найдена.")

async def main():
    print("Бот запущен...")
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
