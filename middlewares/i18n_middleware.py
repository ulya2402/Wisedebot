import json
import os
import logging # Tambahkan logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Chat, User # Impor User
from supabase import Client as SupabaseClient

from bot_config import DEFAULT_LANGUAGE, AVAILABLE_LANGUAGES, LOCALES_DIR
from utils.supabase_interface import get_group_language, get_user_language # Impor get_user_language

translations_cache: Dict[str, Dict[str, str]] = {}

def load_translations(lang_code: str) -> Dict[str, str]:
    if lang_code not in AVAILABLE_LANGUAGES:
        lang_code = DEFAULT_LANGUAGE

    if lang_code in translations_cache:
        return translations_cache[lang_code]

    file_path = os.path.join(LOCALES_DIR, f"{lang_code}.json")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            translations = json.load(f)
            translations_cache[lang_code] = translations
            return translations
    except FileNotFoundError:
        if lang_code != DEFAULT_LANGUAGE:
            logging.warning(f"Translation file for '{lang_code}' not found. Falling back to default '{DEFAULT_LANGUAGE}'.") #
            return load_translations(DEFAULT_LANGUAGE)
        else:
            logging.error(f"Default translation file '{lang_code}.json' not found in '{LOCALES_DIR}'. Returning empty translations.") #
            return {}

class I18nMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        lang_code_to_use = None # Mulai dengan None
        fsm_context = data.get('state')
        supabase_client: SupabaseClient | None = data.get('supabase_client')
        user_obj: User | None = data.get('event_from_user') # Dapatkan objek User dari data
        chat_obj: Chat | None = data.get('event_chat')

        # 1. Coba dari FSM state (prioritas tertinggi untuk alur sementara)
        if fsm_context:
            fsm_data = await fsm_context.get_data()
            lang_code_from_fsm = fsm_data.get('lang_code')
            if lang_code_from_fsm and lang_code_from_fsm in AVAILABLE_LANGUAGES:
                lang_code_to_use = lang_code_from_fsm
                logging.debug(f"I18nMiddleware: Using language from FSM: {lang_code_to_use}")

        # 2. Jika tidak ada dari FSM, coba dari preferensi pengguna (jika ada user_obj dan di DM atau belum ada dari grup)
        if not lang_code_to_use and user_obj and supabase_client:
            logging.debug(f"I18nMiddleware: Attempting to get lang for user ID: {user_obj.id}")
            lang_code_from_user_db = await get_user_language(supabase_client, user_obj.id)
            if lang_code_from_user_db and lang_code_from_user_db in AVAILABLE_LANGUAGES:
                lang_code_to_use = lang_code_from_user_db
                logging.debug(f"I18nMiddleware: Using language from user_preferences: {lang_code_to_use} for user {user_obj.id}")

        # 3. Jika masih belum ada (terutama untuk konteks grup), coba dari pengaturan grup
        if not lang_code_to_use and chat_obj and chat_obj.type != 'private' and supabase_client:
            logging.debug(f"I18nMiddleware: Attempting to get lang for group chat ID: {chat_obj.id}")
            lang_code_from_db = await get_group_language(supabase_client, chat_obj.id)
            logging.debug(f"I18nMiddleware: Language from group_configs DB: {lang_code_from_db} for group {chat_obj.id}")
            if lang_code_from_db and lang_code_from_db in AVAILABLE_LANGUAGES:
                lang_code_to_use = lang_code_from_db

        # 4. Jika semua gagal, fallback ke DEFAULT_LANGUAGE
        if not lang_code_to_use or lang_code_to_use not in AVAILABLE_LANGUAGES:
            lang_code_to_use = DEFAULT_LANGUAGE
            logging.debug(f"I18nMiddleware: Falling back to DEFAULT_LANGUAGE: {lang_code_to_use}")

        current_translations = load_translations(lang_code_to_use)

        # Simpan locale yang digunakan ke dalam objek get_text untuk referensi jika diperlukan
        # Ini adalah cara yang sedikit 'hacky' untuk menyimpan state di dalam fungsi
        # yang akan di-pass, mungkin ada cara yang lebih elegan dengan contextvars
        class GetTextWrapper:
            def __init__(self, translations, locale):
                self.translations = translations
                self.locale = locale

            def __call__(self, key: str, **kwargs) -> str:
                raw_text = self.translations.get(key, f"[{key}]")
                try:
                    return raw_text.format(**kwargs)
                except KeyError as e:
                    logging.warning(f"Missing placeholder {e} for key '{key}' in lang '{self.locale}'. Raw text: '{raw_text}'") #
                    return raw_text
                except Exception as ex:
                    logging.error(f"Error formatting key '{key}' in lang '{self.locale}'. Raw text: '{raw_text}'. Error: {ex}") #
                    return raw_text

        get_text_func = GetTextWrapper(current_translations, lang_code_to_use)

        data["lang_code"] = lang_code_to_use #
        data["lang_name"] = AVAILABLE_LANGUAGES.get(lang_code_to_use, AVAILABLE_LANGUAGES[DEFAULT_LANGUAGE]) #
        data["_"] = get_text_func # Menggunakan instance wrapper

        return await handler(event, data)
