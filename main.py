import asyncio
import os
import logging
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from supabase import create_client, Client as SupabaseClient
from aiogram.enums import ParseMode
from middlewares.i18n_middleware import I18nMiddleware
from handlers.common_handlers import common_router
from handlers.admin_commands import admin_router
from handlers.fsm_handlers import fsm_router
from handlers.ai_response_handlers import ai_response_router
from handlers.user_settings_handlers import user_settings_router
from handlers.moderation_handlers import moderation_router 
from handlers.message_sending_handlers import message_sending_router 
from utils.crypto_interface import CryptoUtil
from aiogram.client.default import DefaultBotProperties
from handlers.welcome_handlers import welcome_router

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def main():
    load_dotenv()
    bot_token = os.environ.get("BOT_TOKEN")
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    encryption_key_str = os.environ.get("ENCRYPTION_KEY")

    if not bot_token:
        logging.error("FATAL: BOT_TOKEN not found. Please set it in your .env file.")
        return
    if not supabase_url or not supabase_key:
        logging.error("FATAL: SUPABASE_URL or SUPABASE_SERVICE_KEY not found. Please set them in your .env file.")
        return
    if not encryption_key_str:
        logging.error("FATAL: ENCRYPTION_KEY not found in .env. Bot cannot run securely.")
        return

    try:
        crypto_util = CryptoUtil(encryption_key_str)
    except ValueError as e:
        logging.error(f"FATAL: Failed to initialize CryptoUtil: {e}. Check your ENCRYPTION_KEY.")
        return

    storage = MemoryStorage()
    default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    bot = Bot(token=bot_token, default=default_props)


    supabase_client: SupabaseClient = create_client(supabase_url, supabase_key)

    workflow_data_for_dp = {
        "supabase_client": supabase_client,
        "crypto_util": crypto_util
    }
    dp = Dispatcher(storage=storage, **workflow_data_for_dp)

    dp.update.outer_middleware(I18nMiddleware())

    dp.include_router(welcome_router)
    dp.include_router(user_settings_router)
    dp.include_router(moderation_router)
    dp.include_router(common_router)
    dp.include_router(admin_router)
    dp.include_router(message_sending_router)
    dp.include_router(ai_response_router)
    dp.include_router(fsm_router)

    

    logging.info("Bot is starting...")
    try:
        await dp.start_polling(bot)
    finally:
        logging.info("Bot is shutting down...")
        await bot.session.close()
        logging.info("Bot session closed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped by admin (KeyboardInterrupt or SystemExit).")
    except Exception as e:
        logging.error(f"An unexpected error occurred at the top level: {e}", exc_info=True)
