import asyncio
from typing import Optional, Union, List, Dict # <<< TAMBAHKAN IMPORT INI
from supabase import Client
from bot_config import (
    DEFAULT_LANGUAGE, AVAILABLE_LANGUAGES, CONVERSATION_HISTORY_LIMIT,
    DEFAULT_MODERATION_LEVEL
)
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
        if response and hasattr(response, 'data') and response.data and response.data.get("language_code") in AVAILABLE_LANGUAGES:
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
            "configured_by_user_id": admin_user_id,
            "last_updated_at": current_time
        }
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
            print(f"Supabase upsert for group {group_id} lang {lang_code} might have failed. Status: {response.status_code if hasattr(response, 'status_code') else 'N/A'}. Data: {response.data if hasattr(response, 'data') else 'N/A'}")
            return False
    except Exception as e:
        error_message = repr(e) if e is not None else "Unknown error (exception object was None)"
        print(f"Error setting language for group {group_id} to {lang_code}: {error_message}")
        return False

async def get_ai_config(supabase: Client, group_id: int) -> Optional[dict]: # Diperbarui
    try:
        response = await asyncio.to_thread(
            supabase.table("group_configs")
            .select(
                "encrypted_groq_api_key, system_prompt, groq_model, "
                "configured_by_user_id, last_updated_at, is_active, language_code, "
                "ai_trigger_command_enabled, ai_trigger_mention_enabled, ai_trigger_custom_prefix, "
                "welcome_message_enabled, custom_welcome_message, welcome_message_ai_enabled, "
                "moderation_level, moderation_action, moderation_text_categories, moderation_image_categories, "
                "ai_welcome_system_prompt"
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
                response.data.setdefault('ai_welcome_system_prompt', None)
            return response.data # response.data bisa None jika maybe_single() tidak menemukan apa pun
        return None
    except Exception as e:
        print(f"Error fetching AI config for group {group_id}: {repr(e)}")
        return None

async def save_ai_config(
    supabase: Client, group_id: int, admin_user_id: int,
    groq_api_key: Optional[str] = None,
    system_prompt: Optional[str] = None,
    groq_model: Optional[str] = None,
    lang_code: Optional[str] = None,
    trigger_command_enabled: Optional[bool] = None,
    trigger_mention_enabled: Optional[bool] = None,
    trigger_custom_prefix: Optional[str] = None, # Ini sudah benar jika string kosong adalah nilai valid, atau bisa juga Optional[str]
    is_active: Optional[bool] = None,
    welcome_message_enabled: Optional[bool] = None,
    custom_welcome_message: Optional[str] = None, # Ini juga bisa Optional[str]
    welcome_message_ai_enabled: Optional[bool] = None,
    moderation_level: Optional[str] = None,
    moderation_action: Optional[str] = None,
    moderation_text_categories: Optional[List] = None, # Menggunakan List dari typing
    moderation_image_categories: Optional[List] = None, # Menggunakan List dari typing
    ai_welcome_system_prompt: Optional[str] = None
    ) -> bool:
    try:
        current_time = datetime.now(timezone.utc).isoformat()
        data_to_upsert: Dict[str, Union[str, int, bool, List, None]] = { # Type hint untuk data_to_upsert
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
        
        # Untuk trigger_custom_prefix, jika None dikirim, kita ingin menghapusnya (atau set NULL di DB)
        # Jika string kosong dikirim, itu juga berarti hapus. DB akan menangani string kosong vs NULL.
        if trigger_custom_prefix is not None: 
            data_to_upsert["ai_trigger_custom_prefix"] = trigger_custom_prefix # Bisa string kosong atau nilai
        
        if welcome_message_enabled is not None: data_to_upsert["welcome_message_enabled"] = welcome_message_enabled
        
        if custom_welcome_message is not None:
             data_to_upsert["custom_welcome_message"] = custom_welcome_message # Bisa string kosong
        
        if welcome_message_ai_enabled is not None: data_to_upsert["welcome_message_ai_enabled"] = welcome_message_ai_enabled
        if moderation_level is not None: data_to_upsert["moderation_level"] = moderation_level
        if moderation_action is not None: data_to_upsert["moderation_action"] = moderation_action
        if moderation_text_categories is not None: data_to_upsert["moderation_text_categories"] = moderation_text_categories
        if moderation_image_categories is not None: data_to_upsert["moderation_image_categories"] = moderation_image_categories
        if ai_welcome_system_prompt is not None: data_to_upsert["ai_welcome_system_prompt"] = ai_welcome_system_prompt


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

async def delete_ai_config(supabase: Client, group_id: int) -> bool:
    try:
        current_time = datetime.now(timezone.utc).isoformat()
        update_data = {
            "encrypted_groq_api_key": None,
            "system_prompt": None,
            "is_active": False,
            "welcome_message_enabled": False,
            "custom_welcome_message": None,
            "welcome_message_ai_enabled": False,
            "moderation_level": DEFAULT_MODERATION_LEVEL,
            "moderation_action": "warn",
            "moderation_text_categories": [],
            "moderation_image_categories": [],
            "ai_welcome_system_prompt": None,
            "last_updated_at": current_time
        }
        response = await asyncio.to_thread(
            supabase.table("group_configs")
            .update(update_data)
            .eq("group_id", group_id)
            .execute
        )
        if hasattr(response, 'status_code') and 200 <= response.status_code < 300:
            return True
        elif hasattr(response, 'data') and response.data is not None:
             return True
        else:
            print(f"Supabase delete (update to null) AI config for group {group_id} failed. Status: {response.status_code if hasattr(response, 'status_code') else 'N/A'}. Data: {response.data if hasattr(response, 'data') else 'N/A'}")
            return False
    except Exception as e:
        print(f"Error deleting AI config for group {group_id}: {repr(e)}")
        return False

async def add_conversation_message(supabase: Client, group_id: int, role: str, content: str) -> bool:
    try:
        data_to_insert = {
            "group_id": group_id,
            "role": role,
            "content": content
        }
        response = await asyncio.to_thread(
            supabase.table("conversation_history").insert(data_to_insert).execute
        )
        if hasattr(response, 'status_code') and response.status_code == 201:
             return True
        elif hasattr(response, 'data') and response.data is not None:
             return True
        else:
            print(f"Supabase insert conversation history for group {group_id} failed. Status: {response.status_code if hasattr(response, 'status_code') else 'N/A'}. Data: {response.data if hasattr(response, 'data') else 'N/A'}")
            return False
    except Exception as e:
        print(f"Error adding conversation message for group {group_id}: {repr(e)}")
        return False

async def get_conversation_history(supabase: Client, group_id: int, limit: int = CONVERSATION_HISTORY_LIMIT) -> List[Dict]: # Diperbarui
    try:
        response = await asyncio.to_thread(
            supabase.table("conversation_history")
            .select("role, content")
            .eq("group_id", group_id)
            .order("timestamp", desc=True)
            .limit(limit)
            .execute
        )
        if response and hasattr(response, 'data') and response.data:
            return response.data[::-1] # type: ignore
        return []
    except Exception as e:
        print(f"Error fetching conversation history for group {group_id}: {repr(e)}")
        return []

async def clear_conversation_history(supabase: Client, group_id: int) -> bool:
    try:
        response = await asyncio.to_thread(
            supabase.table("conversation_history")
            .delete()
            .eq("group_id", group_id)
            .execute
        )
        if hasattr(response, 'status_code') and (response.status_code == 204 or (200 <= response.status_code < 300 and response.data is not None)):
             return True
        elif hasattr(response, 'data') and response.data is not None:
             return True
        else:
            print(f"Supabase delete conversation history for group {group_id} might have failed. Status: {response.status_code if hasattr(response, 'status_code') else 'N/A'}. Data: {response.data if hasattr(response, 'data') else 'N/A'}")
            return False
    except Exception as e:
        print(f"Error clearing conversation history for group {group_id}: {repr(e)}")
        return False

async def get_user_language(supabase: Client, user_id: int) -> Optional[str]: # Diperbarui
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
    try:
        current_time = datetime.now(timezone.utc).isoformat()
        data_to_upsert = {
            "user_id": user_id,
            "language_code": lang_code,
            "last_updated_at": current_time
        }
        response = await asyncio.to_thread(
            supabase.table("user_preferences")
            .upsert(data_to_upsert, on_conflict="user_id")
            .execute
        )
        if hasattr(response, 'status_code') and 200 <= response.status_code < 300:
            return True
        elif hasattr(response, 'data') and response.data is not None:
            return True
        else:
            print(f"Supabase upsert for user {user_id} lang {lang_code} preference might have failed. Status: {response.status_code if hasattr(response, 'status_code') else 'N/A'}. Data: {response.data if hasattr(response, 'data') else 'N/A'}")
            return False
    except Exception as e:
        print(f"Error setting language preference for user {user_id} to {lang_code}: {repr(e)}")
        return False
