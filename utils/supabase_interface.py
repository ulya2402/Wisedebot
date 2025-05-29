import asyncio
from supabase import Client
from bot_config import DEFAULT_LANGUAGE, AVAILABLE_LANGUAGES, CONVERSATION_HISTORY_LIMIT,  DEFAULT_MODERATION_LEVEL
from datetime import datetime, timezone

async def get_group_language(supabase: Client, group_id: int) -> str:
    try:
        response = await asyncio.to_thread(
            supabase.table("group_configs")
            .select("language_code")
            .eq("group_id", group_id)
            .maybe_single()
            .execute
        )
        if response and hasattr(response, 'data') and response.data and response.data.get("language_code") in AVAILABLE_LANGUAGES: #
            return response.data["language_code"]
    except Exception as e:
        error_message = repr(e) if e is not None else "Unknown error (exception object was None)"
        print(f"Error fetching language for group {group_id}: {error_message}")
    return DEFAULT_LANGUAGE

async def set_group_language(supabase: Client, group_id: int, lang_code: str, admin_user_id: int) -> bool:
    try:
        current_time = datetime.now(timezone.utc).isoformat()
        data_to_upsert = {
            "group_id": group_id,
            "language_code": lang_code,
            "configured_by_user_id": admin_user_id, #
            "last_updated_at": current_time
        }
        response = await asyncio.to_thread(
            supabase.table("group_configs")
            .upsert(data_to_upsert, on_conflict="group_id")
            .execute
        )
        if hasattr(response, 'status_code') and 200 <= response.status_code < 300: #
             return True
        elif hasattr(response, 'data') and response.data is not None: #
             return True
        else:
            print(f"Supabase upsert for group {group_id} lang {lang_code} might have failed. Status: {response.status_code if hasattr(response, 'status_code') else 'N/A'}. Data: {response.data if hasattr(response, 'data') else 'N/A'}")
            return False
    except Exception as e:
        error_message = repr(e) if e is not None else "Unknown error (exception object was None)"
        print(f"Error setting language for group {group_id} to {lang_code}: {error_message}")
        return False

async def get_ai_config(supabase: Client, group_id: int):
    try:
        response = await asyncio.to_thread(
            supabase.table("group_configs")
            .select(
                "encrypted_groq_api_key, system_prompt, groq_model, "
                "configured_by_user_id, last_updated_at, is_active, language_code, "
                "ai_trigger_command_enabled, ai_trigger_mention_enabled, ai_trigger_custom_prefix, "
                "welcome_message_enabled, custom_welcome_message, welcome_message_ai_enabled, "
                "moderation_level, moderation_action, moderation_text_categories, moderation_image_categories"
            )
            .eq("group_id", group_id)
            .maybe_single()
            .execute
        )
        if response and hasattr(response, 'data'):
            if response.data:
                response.data.setdefault('ai_trigger_command_enabled', True)
                response.data.setdefault('ai_trigger_mention_enabled', True)
                response.data.setdefault('ai_trigger_custom_prefix', None)
                response.data.setdefault('welcome_message_enabled', False)
                response.data.setdefault('custom_welcome_message', None)
                response.data.setdefault('welcome_message_ai_enabled', False)
                response.data.setdefault('moderation_level', DEFAULT_MODERATION_LEVEL)
                response.data.setdefault('moderation_action', 'warn')
                response.data.setdefault('moderation_text_categories', [])
                response.data.setdefault('moderation_image_categories', [])
            return response.data
        return None
    except Exception as e:
        print(f"Error fetching AI config for group {group_id}: {repr(e)}")
        return None

async def save_ai_config(
    supabase: Client, group_id: int, admin_user_id: int,
    groq_api_key: str | None = None,
    system_prompt: str | None = None,
    groq_model: str | None = None,
    lang_code: str | None = None,
    trigger_command_enabled: bool | None = None,
    trigger_mention_enabled: bool | None = None,
    trigger_custom_prefix: str | None = None,
    is_active: bool | None = None,
    welcome_message_enabled: bool | None = None,
    custom_welcome_message: str | None = None,
    welcome_message_ai_enabled: bool | None = None,
    moderation_level: str | None = None,
    moderation_action: str | None = None,
    moderation_text_categories: list | None = None,
    moderation_image_categories: list | None = None
    ) -> bool:
    try:
        current_time = datetime.now(timezone.utc).isoformat()
        data_to_upsert = {
            "group_id": group_id,
            "configured_by_user_id": admin_user_id,
            "last_updated_at": current_time,
        }

        if groq_api_key is not None: data_to_upsert["encrypted_groq_api_key"] = groq_api_key
        if system_prompt is not None: data_to_upsert["system_prompt"] = system_prompt
        if groq_model is not None: data_to_upsert["groq_model"] = groq_model
        if lang_code is not None: data_to_upsert["language_code"] = lang_code
        if is_active is not None: data_to_upsert["is_active"] = is_active
        if trigger_command_enabled is not None: data_to_upsert["ai_trigger_command_enabled"] = trigger_command_enabled
        if trigger_mention_enabled is not None: data_to_upsert["ai_trigger_mention_enabled"] = trigger_mention_enabled
        if trigger_custom_prefix is not None:
            data_to_upsert["ai_trigger_custom_prefix"] = trigger_custom_prefix if trigger_custom_prefix else None
        if welcome_message_enabled is not None: data_to_upsert["welcome_message_enabled"] = welcome_message_enabled
        if custom_welcome_message is not None:
            data_to_upsert["custom_welcome_message"] = custom_welcome_message
        if welcome_message_ai_enabled is not None: data_to_upsert["welcome_message_ai_enabled"] = welcome_message_ai_enabled
        if moderation_level is not None: data_to_upsert["moderation_level"] = moderation_level
        if moderation_action is not None: data_to_upsert["moderation_action"] = moderation_action
        if moderation_text_categories is not None: data_to_upsert["moderation_text_categories"] = moderation_text_categories
        if moderation_image_categories is not None: data_to_upsert["moderation_image_categories"] = moderation_image_categories


        update_fields_count = len(data_to_upsert) - 3
        if update_fields_count <= 0:
             print(f"No actual data provided to save_ai_config for group {group_id}, skipping upsert.")
             return True


        response = await asyncio.to_thread(
            supabase.table("group_configs")
            .upsert(data_to_upsert, on_conflict="group_id")
            .execute
        )
        if hasattr(response, 'status_code') and 200 <= response.status_code < 300:
             return True
        elif hasattr(response, 'data') and response.data is not None:
             return True
        else:
            print(f"Supabase upsert AI config for group {group_id} failed. Status: {response.status_code if hasattr(response, 'status_code') else 'N/A'}. Data: {response.data if hasattr(response, 'data') else 'N/A'}")
            return False
    except Exception as e:
        print(f"Error saving AI config for group {group_id}: {repr(e)}")
        return False


async def delete_ai_config(supabase: Client, group_id: int) -> bool: #
    try:
        current_time = datetime.now(timezone.utc).isoformat()
        update_data = {
            "encrypted_groq_api_key": None, #
            "system_prompt": None, #
            "is_active": False, #
            "welcome_message_enabled": False,
            "custom_welcome_message": None,
            "welcome_message_ai_enabled": False, # Reset kolom baru
            "last_updated_at": current_time #
        }
        response = await asyncio.to_thread(
            supabase.table("group_configs")
            .update(update_data)
            .eq("group_id", group_id)
            .execute
        )
        if hasattr(response, 'status_code') and 200 <= response.status_code < 300: #
            return True
        elif hasattr(response, 'data') and response.data is not None: #
             return True
        else:
            print(f"Supabase delete (update to null) AI config for group {group_id} failed. Status: {response.status_code if hasattr(response, 'status_code') else 'N/A'}. Data: {response.data if hasattr(response, 'data') else 'N/A'}")
            return False
    except Exception as e:
        print(f"Error deleting AI config for group {group_id}: {repr(e)}")
        return False

async def add_conversation_message(supabase: Client, group_id: int, role: str, content: str) -> bool: #
    try:
        data_to_insert = {
            "group_id": group_id,
            "role": role,
            "content": content
        }
        response = await asyncio.to_thread(
            supabase.table("conversation_history").insert(data_to_insert).execute #
        )
        if hasattr(response, 'status_code') and response.status_code == 201: #
             return True
        elif hasattr(response, 'data') and response.data is not None: #
             return True
        else:
            print(f"Supabase insert conversation history for group {group_id} failed. Status: {response.status_code if hasattr(response, 'status_code') else 'N/A'}. Data: {response.data if hasattr(response, 'data') else 'N/A'}")
            return False
    except Exception as e:
        print(f"Error adding conversation message for group {group_id}: {repr(e)}")
        return False

async def get_conversation_history(supabase: Client, group_id: int, limit: int = CONVERSATION_HISTORY_LIMIT) -> list[dict]: #
    try:
        response = await asyncio.to_thread(
            supabase.table("conversation_history") #
            .select("role, content") #
            .eq("group_id", group_id) #
            .order("timestamp", desc=True) #
            .limit(limit) #
            .execute
        )
        if response and hasattr(response, 'data') and response.data: #
            return response.data[::-1]
        return []
    except Exception as e:
        print(f"Error fetching conversation history for group {group_id}: {repr(e)}")
        return []

async def clear_conversation_history(supabase: Client, group_id: int) -> bool: #
    try:
        response = await asyncio.to_thread(
            supabase.table("conversation_history") #
            .delete() #
            .eq("group_id", group_id) #
            .execute
        )
        if hasattr(response, 'status_code') and (response.status_code == 204 or (200 <= response.status_code < 300 and response.data is not None)): #
             return True
        elif hasattr(response, 'data') and response.data is not None: #
             return True
        else:
            print(f"Supabase delete conversation history for group {group_id} might have failed. Status: {response.status_code if hasattr(response, 'status_code') else 'N/A'}. Data: {response.data if hasattr(response, 'data') else 'N/A'}")
            return False
    except Exception as e:
        print(f"Error clearing conversation history for group {group_id}: {repr(e)}")
        return False

# ... (semua fungsi yang sudah ada sebelumnya: get_group_language, set_group_language, get_ai_config, save_ai_config, delete_ai_config, add_conversation_message, get_conversation_history, clear_conversation_history) ...

async def get_user_language(supabase: Client, user_id: int) -> str | None:
    """
    Mengambil preferensi bahasa pengguna dari tabel user_preferences.
    Mengembalikan kode bahasa jika ditemukan, atau None jika tidak.
    """
    try:
        response = await asyncio.to_thread(
            supabase.table("user_preferences")
            .select("language_code")
            .eq("user_id", user_id)
            .maybe_single()
            .execute
        )
        if response and hasattr(response, 'data') and response.data and response.data.get("language_code"):
            return response.data["language_code"]
        return None
    except Exception as e:
        print(f"Error fetching language preference for user {user_id}: {repr(e)}")
        return None

async def set_user_language(supabase: Client, user_id: int, lang_code: str) -> bool:
    """
    Menyimpan atau memperbarui preferensi bahasa pengguna di tabel user_preferences.
    Mengembalikan True jika berhasil, False jika gagal.
    """
    try:
        current_time = datetime.now(timezone.utc).isoformat()
        data_to_upsert = {
            "user_id": user_id,
            "language_code": lang_code,
            "last_updated_at": current_time
        }
        response = await asyncio.to_thread(
            supabase.table("user_preferences")
            .upsert(data_to_upsert, on_conflict="user_id") # 'user_id' adalah kolom konflik
            .execute
        )
        if hasattr(response, 'status_code') and 200 <= response.status_code < 300:
            return True
        elif hasattr(response, 'data') and response.data is not None: # Upsert sukses bisa mengembalikan data atau tidak
            return True
        else:
            print(f"Supabase upsert for user {user_id} lang {lang_code} preference might have failed. Status: {response.status_code if hasattr(response, 'status_code') else 'N/A'}. Data: {response.data if hasattr(response, 'data') else 'N/A'}")
            return False
    except Exception as e:
        print(f"Error setting language preference for user {user_id} to {lang_code}: {repr(e)}")
        return False
