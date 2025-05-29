import asyncio
import logging
from aiogram import Bot, Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.enums import ChatMemberStatus
from aiogram.utils.keyboard import InlineKeyboardBuilder
from supabase import Client as SupabaseClient
from datetime import datetime
from utils.helpers import escape_html_tags
from states.setup_states import AISetupStates
from utils.supabase_interface import get_ai_config, get_group_language, delete_ai_config, save_ai_config
from bot_config import (
    DEFAULT_GROQ_MODEL, AVAILABLE_LANGUAGES, DEFAULT_LANGUAGE,
    AVAILABLE_GROQ_MODELS, get_model_display_name,
    MODERATION_LEVELS, DEFAULT_MODERATION_LEVEL
)
from middlewares.i18n_middleware import load_translations

admin_router = Router()
TRIGGERS_CALLBACK_PREFIX = "aitrig:"
MODERATION_CALLBACK_PREFIX = "modcfg:"

async def is_admin(bot_instance: Bot, chat_id: int, user_id: int) -> bool:
    member = await bot_instance.get_chat_member(chat_id, user_id)
    return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]

async def build_triggers_menu(
    bot_instance: Bot,
    supabase_client: SupabaseClient,
    group_id: int,
    raw_group_name_from_fsm: str,
    bot_username_from_fsm: str,
    lang_code_for_dm: str
):
    current_dm_translations = load_translations(lang_code_for_dm)
    def get_menu_text(key, **kwargs):
        default_val = f"[{key}]" 
        if 'default_text' in kwargs: 
            default_val = kwargs.pop('default_text')
        escaped_kwargs = {k: escape_html_tags(v) if isinstance(v, str) else v for k, v in kwargs.items()}
        return current_dm_translations.get(key, default_val).format(**escaped_kwargs)

    config = await get_ai_config(supabase_client, group_id)

    current_raw_group_name = raw_group_name_from_fsm
    if not current_raw_group_name or current_raw_group_name == "this group":
        try:
            chat_info = await bot_instance.get_chat(group_id)
            if chat_info and chat_info.title:
                current_raw_group_name = chat_info.title
        except Exception as e:
            print(f"DEBUG build_triggers_menu: Could not fetch group title for {group_id}: {e}")

    if not config:
        config = {"ai_trigger_command_enabled": True, "ai_trigger_mention_enabled": True, "ai_trigger_custom_prefix": None}

    cmd_enabled = config.get('ai_trigger_command_enabled', True)
    mention_enabled = config.get('ai_trigger_mention_enabled', True)
    custom_prefix = config.get('ai_trigger_custom_prefix')

    text_kwargs_title = {"group_name": current_raw_group_name}

    text = get_menu_text("ai_triggers_menu_title", **text_kwargs_title) + "\n\n"
    text += f"1. {get_menu_text('trigger_ask_ai_command')}: <b>{get_menu_text('status_enabled') if cmd_enabled else get_menu_text('status_disabled')}</b>\n"
    text += f"2. {get_menu_text('trigger_bot_mention', bot_username=f'@{bot_username_from_fsm}')}: <b>{get_menu_text('status_enabled') if mention_enabled else get_menu_text('status_disabled')}</b>\n"
    text += f"3. {get_menu_text('trigger_custom_prefix')}: {f'<code>{escape_html_tags(custom_prefix)}</code>' if custom_prefix else get_menu_text('status_not_set')}\n"

    builder = InlineKeyboardBuilder()
    builder.button(
        text=get_menu_text("button_toggle_ask_ai_cmd") + (f" ({get_menu_text('status_disabled')})" if not cmd_enabled else f" ({get_menu_text('status_enabled')})"),
        callback_data=f"{TRIGGERS_CALLBACK_PREFIX}toggle_cmd"
    )
    builder.button(
        text=get_menu_text("button_toggle_mention") + (f" ({get_menu_text('status_disabled')})" if not mention_enabled else f" ({get_menu_text('status_enabled')})"),
        callback_data=f"{TRIGGERS_CALLBACK_PREFIX}toggle_mention"
    )
    builder.button(text=get_menu_text("button_set_custom_prefix"), callback_data=f"{TRIGGERS_CALLBACK_PREFIX}set_prefix")
    if custom_prefix:
        builder.button(text=get_menu_text("button_remove_custom_prefix"), callback_data=f"{TRIGGERS_CALLBACK_PREFIX}remove_prefix")
    builder.button(text=get_menu_text("button_done_triggers"), callback_data=f"{TRIGGERS_CALLBACK_PREFIX}done")
    builder.adjust(1,1,2,1)
    return text, builder.as_markup()

async def build_moderation_menu(
    supabase_client: SupabaseClient,
    group_id: int,
    raw_group_name_from_fsm: str,
    lang_code_for_dm: str
):
    current_dm_translations = load_translations(lang_code_for_dm)
    def get_menu_text(key, **kwargs):
        default_val = f"[{key}]"
        if 'default_text' in kwargs:
            default_val = kwargs.pop('default_text')
        escaped_kwargs = {k: escape_html_tags(v) if isinstance(v, str) else v for k, v in kwargs.items()}
        return current_dm_translations.get(key, default_val).format(**escaped_kwargs)

    config = await get_ai_config(supabase_client, group_id)
    current_level_code = config.get('moderation_level', DEFAULT_MODERATION_LEVEL) if config else DEFAULT_MODERATION_LEVEL

    level_display_name_key = f"moderation_level_{current_level_code}"
    level_display_name_default = MODERATION_LEVELS.get(current_level_code, current_level_code.capitalize())
    level_display_name = get_menu_text(level_display_name_key, default_text=level_display_name_default)

    menu_text = get_menu_text("moderation_menu_title_dm", group_name=raw_group_name_from_fsm) + "\n"
    menu_text += get_menu_text("moderation_current_level_dm", level=escape_html_tags(level_display_name)) + "\n\n"
    menu_text += get_menu_text("moderation_select_level_prompt_dm")

    builder = InlineKeyboardBuilder()
    for level_code, level_name_default_text in MODERATION_LEVELS.items():
        loc_key = f"moderation_level_{level_code}"
        display_name = get_menu_text(loc_key, default_text=level_name_default_text)
        button_text = f"{display_name}"
        if current_level_code == level_code:
            button_text = f"✅ {button_text}"
        builder.button(text=button_text, callback_data=f"{MODERATION_CALLBACK_PREFIX}setlevel_{level_code}")

    builder.button(text=get_menu_text("button_done_moderation_dm"), callback_data=f"{MODERATION_CALLBACK_PREFIX}done")
    builder.adjust(1)
    return menu_text, builder.as_markup()


@admin_router.message(Command("setup_ai"))
async def cmd_setup_ai(message: types.Message, state: FSMContext, supabase_client: SupabaseClient, _: callable, bot: Bot):
    if message.chat.type == 'private':
        await message.answer(_("command_only_in_group"))
        return

    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.answer(_("admin_only_command"))
        return

    group_id = message.chat.id
    raw_group_name = message.chat.title if message.chat.title else "this group"
    admin_user_id = message.from_user.id

    existing_config = await get_ai_config(supabase_client, group_id)
    group_lang_for_dm = await get_group_language(supabase_client, group_id)

    dm_translations = load_translations(group_lang_for_dm)
    def get_dm_text(key, **kwargs):
        escaped_kwargs = {k: escape_html_tags(v) if isinstance(v, str) else v for k, v in kwargs.items()}
        return dm_translations.get(key, f"[{key}]").format(**escaped_kwargs)

    if existing_config and existing_config.get("encrypted_groq_api_key"):
        raw_admin_username_config = str(existing_config["configured_by_user_id"])
        try:
            admin_info_config = await bot.get_chat(existing_config["configured_by_user_id"])
            if admin_info_config and admin_info_config.username:
                raw_admin_username_config = admin_info_config.username
        except Exception:
            pass

        last_updated_dt_config = datetime.fromisoformat(existing_config["last_updated_at"])
        raw_formatted_date_config = last_updated_dt_config.strftime("%d %B %Y, %H:%M %Z")

        text_kwargs = { "group_name": raw_group_name, "admin_username": raw_admin_username_config, "date": raw_formatted_date_config }
        text = get_dm_text("confirm_config_overwrite_prompt_dm", **text_kwargs)

        builder = InlineKeyboardBuilder()
        cb_group_name = raw_group_name.replace(":", "-")
        builder.button(text=get_dm_text("button_yes_overwrite"), callback_data=f"overwrite_confirm_yes:{group_id}:{cb_group_name}:{group_lang_for_dm}")
        builder.button(text=get_dm_text("button_no_keep_existing"), callback_data=f"overwrite_confirm_no:{group_id}:{cb_group_name}:{group_lang_for_dm}")

        try:
            await bot.send_message(admin_user_id, text, reply_markup=builder.as_markup())
            await message.answer(_("setup_dm_check_dm_prompt"))
        except Exception as e:
            await message.answer(_("dm_send_error_prompt"))
            print(f"Error cmd_setup_ai sending DM for overwrite: {repr(e)}")
    else:
        try:
            text = get_dm_text("setup_ai_admin_dm_start_new", group_name=raw_group_name)
            builder = InlineKeyboardBuilder()
            cb_group_name = raw_group_name.replace(":", "-")
            builder.button(text=get_dm_text("button_start_setup_dm"), callback_data=f"start_new_setup:{group_id}:{cb_group_name}:{group_lang_for_dm}")

            await bot.send_message(admin_user_id, text, reply_markup=builder.as_markup())
            await message.answer(_("setup_dm_check_dm_prompt"))
        except Exception as e:
            await message.answer(_("dm_send_error_prompt"))
            print(f"Error cmd_setup_ai sending DM for new setup: {repr(e)}")

@admin_router.callback_query(F.data.startswith("start_new_setup:"))
async def cq_start_new_setup(callback_query: types.CallbackQuery, state: FSMContext, _: callable):
    try:
        parts = callback_query.data.split(":", 3)
        if len(parts) < 4: raise ValueError("Callback data format error for start_new_setup")
        _, group_id_str, raw_group_name_from_cb, group_lang_for_dm = parts
        group_id = int(group_id_str)
    except ValueError as e:
        print(f"Error cq_start_new_setup parsing callback_data: {callback_query.data}, Error: {e}")
        await callback_query.answer(_("generic_error") + " (Invalid callback data)", show_alert=True); return

    await state.set_state(AISetupStates.awaiting_groq_key)
    await state.update_data(group_id_to_configure=group_id, group_name_to_configure=raw_group_name_from_cb, lang_code=group_lang_for_dm )

    dm_translations = load_translations(group_lang_for_dm)
    def get_dm_prompt_text_local(key, **kwargs):
        escaped_kwargs = {k: escape_html_tags(v) if isinstance(v, str) else v for k, v in kwargs.items()}
        return dm_translations.get(key, f"[{key}]").format(**escaped_kwargs)

    builder = InlineKeyboardBuilder()
    builder.button(text=get_dm_prompt_text_local("button_get_groq_api_key"), url="https://console.groq.com/keys")
    await callback_query.message.edit_text(get_dm_prompt_text_local("request_groq_key_dm"), reply_markup=builder.as_markup(resize_keyboard=True))
    await callback_query.answer()

@admin_router.callback_query(F.data.startswith("overwrite_confirm_yes:"))
async def cq_overwrite_yes(callback_query: types.CallbackQuery, state: FSMContext, _: callable):
    try:
        parts = callback_query.data.split(":", 3)
        if len(parts) < 4: raise ValueError("Callback data format error for overwrite_confirm_yes")
        _, group_id_str, raw_group_name_from_cb, group_lang_for_dm = parts
        group_id = int(group_id_str)
    except ValueError as e:
        print(f"Error cq_overwrite_yes parsing callback_data: {callback_query.data}, Error: {e}")
        await callback_query.answer(_("generic_error") + " (Invalid callback data)", show_alert=True); return

    await state.set_state(AISetupStates.awaiting_groq_key)
    await state.update_data(group_id_to_configure=group_id, group_name_to_configure=raw_group_name_from_cb, lang_code=group_lang_for_dm)

    dm_translations = load_translations(group_lang_for_dm)
    def get_dm_prompt_text_local(key, **kwargs):
        escaped_kwargs = {k: escape_html_tags(v) if isinstance(v, str) else v for k, v in kwargs.items()}
        return dm_translations.get(key, f"[{key}]").format(**escaped_kwargs)

    builder = InlineKeyboardBuilder()
    builder.button(text=get_dm_prompt_text_local("button_get_groq_api_key"), url="https://console.groq.com/keys")
    await callback_query.message.edit_text(get_dm_prompt_text_local("request_groq_key_dm"), reply_markup=builder.as_markup(resize_keyboard=True))
    await callback_query.answer()

@admin_router.callback_query(F.data.startswith("overwrite_confirm_no:"))
async def cq_overwrite_no(callback_query: types.CallbackQuery, state: FSMContext, _: callable):
    try:
        parts = callback_query.data.split(":", 3)
        if len(parts) < 4:
            _, group_id_str, raw_group_name_from_cb = callback_query.data.split(":", 2)
            lang_code_for_dm = DEFAULT_LANGUAGE
        else:
            _, group_id_str, raw_group_name_from_cb, lang_code_for_dm = parts
    except ValueError as e:
        print(f"Error cq_overwrite_no parsing callback_data: {callback_query.data}, Error: {e}")
        await callback_query.answer(_("generic_error") + " (Invalid callback data)", show_alert=True); return

    dm_translations = load_translations(lang_code_for_dm)
    def get_dm_text_local(key, **kwargs):
        escaped_kwargs = {k: escape_html_tags(v) if isinstance(v, str) else v for k, v in kwargs.items()}
        return dm_translations.get(key, f"[{key}]").format(**escaped_kwargs)

    await callback_query.message.edit_text(get_dm_text_local("config_not_overwritten_dm", group_name=raw_group_name_from_cb))
    await state.clear()
    await callback_query.answer()

@admin_router.message(Command("get_ai_config"))
async def cmd_get_ai_config(message: types.Message, supabase_client: SupabaseClient, _: callable, bot: Bot):
    if message.chat.type == 'private':
        await message.answer(_("command_only_in_group"))
        return
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.answer(_("admin_only_command"))
        return
    group_id = message.chat.id
    raw_group_name = message.chat.title if message.chat.title else "this group"
    config = await get_ai_config(supabase_client, group_id)
    admin_user_id = message.from_user.id
    group_lang_for_dm_display = await get_group_language(supabase_client, group_id)

    dm_translations = load_translations(group_lang_for_dm_display)
    def get_dm_text_display(key, **kwargs):
        default_text_val = f"[{key}]"
        if 'default_text' in kwargs: # Check if 'default_text' was passed
            default_text_val = kwargs.pop('default_text')
        escaped_kwargs = {k: escape_html_tags(v) if isinstance(v, str) else v for k, v in kwargs.items()}
        return dm_translations.get(key, default_text_val).format(**escaped_kwargs)

    if config and config.get("encrypted_groq_api_key"):
        raw_masked_key = config["encrypted_groq_api_key"][:7] + "****" if config["encrypted_groq_api_key"] else get_dm_text_display("not_set")
        raw_admin_username_config = str(config["configured_by_user_id"])
        try:
            admin_info_config = await bot.get_chat(config["configured_by_user_id"])
            if admin_info_config and admin_info_config.username: raw_admin_username_config = admin_info_config.username
        except Exception: pass
        last_updated_dt_config = datetime.fromisoformat(config["last_updated_at"])
        raw_formatted_date_config = last_updated_dt_config.strftime("%d %B %Y, %H:%M %Z")
        status_text_key = "status_active" if config.get("is_active", False) else "status_inactive"
        status_text = get_dm_text_display(status_text_key)
        current_config_lang_code = config.get("language_code", group_lang_for_dm_display)
        if current_config_lang_code not in AVAILABLE_LANGUAGES: current_config_lang_code = DEFAULT_LANGUAGE
        lang_name_display_config = AVAILABLE_LANGUAGES.get(current_config_lang_code)
        raw_system_prompt = config["system_prompt"] or get_dm_text_display("not_set")
        raw_groq_model_id = config.get("groq_model", DEFAULT_GROQ_MODEL)
        raw_groq_model_display = get_model_display_name(raw_groq_model_id)

        current_moderation_level_code = config.get('moderation_level', DEFAULT_MODERATION_LEVEL)
        moderation_level_name_key = f"moderation_level_{current_moderation_level_code}"
        moderation_level_default_text = MODERATION_LEVELS.get(current_moderation_level_code, current_moderation_level_code.capitalize())
        moderation_level_display = get_dm_text_display(moderation_level_name_key, default_text=moderation_level_default_text)


        text = get_dm_text_display("get_ai_config_title_dm", group_name=raw_group_name) + "\n"
        text += get_dm_text_display("get_ai_config_lang_dm", language_name=lang_name_display_config) + "\n"
        text += get_dm_text_display("get_ai_config_api_key_masked_dm", masked_api_key=raw_masked_key) + "\n"
        text += get_dm_text_display("get_ai_config_system_prompt_dm", system_prompt=raw_system_prompt) + "\n"
        text += get_dm_text_display("get_ai_config_groq_model_dm", groq_model=raw_groq_model_display) + "\n"
        text += get_dm_text_display("get_ai_config_set_by_dm", admin_username=raw_admin_username_config, user_id=str(config["configured_by_user_id"])) + "\n"
        text += get_dm_text_display("get_ai_config_last_updated_dm", date=raw_formatted_date_config) + "\n"
        text += get_dm_text_display("get_ai_config_active_status_dm", status=status_text) + "\n"
        text += get_dm_text_display("get_moderation_config_level_dm", level=moderation_level_display)


        try:
            await bot.send_message(admin_user_id, text)
            if message.chat.id != admin_user_id : await message.answer(_("config_sent_to_dm"))
        except Exception as e: print(f"Error cmd_get_ai_config sending DM: {repr(e)}"); await message.answer(_("dm_send_error_prompt"))
    else:
        try:
            await bot.send_message(admin_user_id, get_dm_text_display("get_ai_config_no_config_dm", group_name=raw_group_name))
            if message.chat.id != admin_user_id : await message.answer(_("config_sent_to_dm"))
        except Exception as e: print(f"Error cmd_get_ai_config sending no_config DM: {repr(e)}"); await message.answer(_("dm_send_error_prompt"))

@admin_router.message(Command("reset_ai_config"))
async def cmd_reset_ai_config(message: types.Message, state: FSMContext, supabase_client: SupabaseClient, _: callable, bot: Bot):
    if message.chat.type == 'private': await message.answer(_("command_only_in_group")); return
    if not await is_admin(bot, message.chat.id, message.from_user.id): await message.answer(_("admin_only_command")); return
    group_id = message.chat.id
    raw_group_name = message.chat.title if message.chat.title else "this group"
    admin_user_id = message.from_user.id
    config = await get_ai_config(supabase_client, group_id)
    group_lang_for_dm_reset = await get_group_language(supabase_client, group_id)

    dm_translations_reset = load_translations(group_lang_for_dm_reset)
    def get_dm_text_reset(key, **kwargs):
        escaped_kwargs = {k: escape_html_tags(v) if isinstance(v, str) else v for k, v in kwargs.items()}
        return dm_translations_reset.get(key, f"[{key}]").format(**escaped_kwargs)
    if not config or not config.get("encrypted_groq_api_key"):
        try:
            await bot.send_message(admin_user_id, get_dm_text_reset("reset_ai_config_no_config_dm", group_name=raw_group_name))
            if message.chat.id != admin_user_id : await message.answer(_("config_sent_to_dm"))
        except Exception as e: print(f"Error cmd_reset_ai_config sending no_config DM: {repr(e)}"); await message.answer(_("dm_send_error_prompt"))
        return
    try:
        builder = InlineKeyboardBuilder()
        cb_group_name = raw_group_name.replace(":", "-")
        base_cb_data_reset = f"{group_id}:{cb_group_name}:{group_lang_for_dm_reset}"
        builder.button(text=get_dm_text_reset("button_yes_delete_config_dm"), callback_data=f"reset_ai_yes:{base_cb_data_reset}")
        builder.button(text=get_dm_text_reset("button_no_cancel_delete_dm"), callback_data=f"reset_ai_no:{base_cb_data_reset}")
        await bot.send_message(admin_user_id, get_dm_text_reset("reset_ai_config_confirm_prompt_dm", group_name=raw_group_name), reply_markup=builder.as_markup())
        if message.chat.id != admin_user_id : await message.answer(_("reset_check_dm_prompt"))
    except Exception as e: print(f"Error cmd_reset_ai_config sending confirmation DM: {repr(e)}"); await message.answer(_("dm_send_error_prompt"))

@admin_router.callback_query(F.data.startswith("reset_ai_yes:"))
async def cq_reset_confirm_yes(callback_query: types.CallbackQuery, state: FSMContext, supabase_client: SupabaseClient, _: callable, bot: Bot):
    await state.clear()
    try:
        parts = callback_query.data.split(":")
        group_id = int(parts[2])
        raw_group_name_from_cb = parts[3]
        lang_code = parts[4]
    except (IndexError, ValueError) as e:
        print(f"Error cq_reset_confirm_yes parsing callback_data: {callback_query.data}, Error: {repr(e)}")
        await callback_query.answer(_("generic_error") + " (Invalid callback data)", show_alert=True); return

    dm_translations = load_translations(lang_code)
    def get_dm_text_local(key, **kwargs):
        escaped_kwargs = {k: escape_html_tags(v) if isinstance(v, str) else v for k, v in kwargs.items()}
        return dm_translations.get(key, f"[{key}]").format(**escaped_kwargs)
    success = await delete_ai_config(supabase_client, group_id)
    if success:
        await callback_query.message.edit_text(get_dm_text_local("config_deleted_success_dm", group_name=raw_group_name_from_cb))
        try:
            group_actual_lang = await get_group_language(supabase_client, group_id)
            group_translations_notif = load_translations(group_actual_lang)
            def get_group_notif_text_local(key): return group_translations_notif.get(key, f"[{key}]")
            await bot.send_message(group_id, get_group_notif_text_local("config_delete_group_notification"))
        except Exception as e: print(f"Failed to send reset notification to group {group_id}: {repr(e)}")
    else: await callback_query.message.edit_text(get_dm_text_local("generic_error"))
    await callback_query.answer()

@admin_router.callback_query(F.data.startswith("reset_ai_no:"))
async def cq_reset_confirm_no(callback_query: types.CallbackQuery, state: FSMContext, _: callable):
    await state.clear()
    try:
        parts = callback_query.data.split(":")
        raw_group_name_from_cb = parts[3]
        lang_code = parts[4]
    except (IndexError, ValueError) as e:
        print(f"Error cq_reset_confirm_no parsing callback_data: {callback_query.data}, Error: {repr(e)}")
        await callback_query.answer(_("generic_error") + " (Invalid callback data)", show_alert=True); return

    dm_translations = load_translations(lang_code)
    def get_dm_text_local(key, **kwargs):
        escaped_kwargs = {k: escape_html_tags(v) if isinstance(v, str) else v for k, v in kwargs.items()}
        return dm_translations.get(key, f"[{key}]").format(**escaped_kwargs)
    await callback_query.message.edit_text(get_dm_text_local("config_not_deleted_dm", group_name=raw_group_name_from_cb))
    await callback_query.answer()

@admin_router.message(Command("set_ai_triggers"))
async def cmd_set_ai_triggers(message: types.Message, state: FSMContext, supabase_client: SupabaseClient, _: callable, bot: Bot):
    if message.chat.type == 'private':
        await message.answer(_("command_only_in_group")); return
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.answer(_("admin_only_command")); return

    admin_user_id = message.from_user.id
    group_id = message.chat.id
    raw_group_name = message.chat.title or "this group"
    group_lang_for_dm = await get_group_language(supabase_client, group_id)
    bot_username_obj = await bot.get_me()
    bot_username_str = bot_username_obj.username if bot_username_obj.username else "YourBot"

    storage = state.storage
    dm_key = StorageKey(bot_id=bot.id, chat_id=admin_user_id, user_id=admin_user_id)
    dm_fsm_context = FSMContext(storage=storage, key=dm_key)

    await dm_fsm_context.set_state(AISetupStates.awaiting_trigger_prefix)
    await dm_fsm_context.update_data(
        trigger_config_group_id=group_id,
        trigger_config_lang_code=group_lang_for_dm,
        trigger_config_bot_username=bot_username_str,
        trigger_config_group_name=raw_group_name
    )

    text, keyboard = await build_triggers_menu(
        bot, supabase_client, group_id, raw_group_name, bot_username_str, group_lang_for_dm
    )

    try:
        await bot.send_message(admin_user_id, text, reply_markup=keyboard)
        await message.answer(_("trigger_config_sent_to_dm"))
    except Exception as e:
        logging.error(f"Error in cmd_set_ai_triggers sending DM: {e}")
        await message.answer(_("dm_send_error_prompt"))

@admin_router.callback_query(StateFilter(AISetupStates.awaiting_trigger_prefix), F.data.startswith(TRIGGERS_CALLBACK_PREFIX))
async def cq_ai_triggers_handler(callback_query: types.CallbackQuery, state: FSMContext, supabase_client: SupabaseClient, bot: Bot):
    fsm_data = await state.get_data()
    group_id = fsm_data.get("trigger_config_group_id")
    lang_code_for_dm = fsm_data.get("trigger_config_lang_code", DEFAULT_LANGUAGE)
    bot_username = fsm_data.get("trigger_config_bot_username", "YourBot")
    raw_group_name = fsm_data.get("trigger_config_group_name", "this group")

    if not group_id:
        await callback_query.answer("Error: Session expired. Please use /set_ai_triggers in group again.", show_alert=True)
        return

    dm_translations = load_translations(lang_code_for_dm)
    def get_dm_trigger_text(key, **kwargs):
        default_val = f"[{key}]"
        if 'default_text' in kwargs:
            default_val = kwargs.pop('default_text')
        escaped_kwargs = {k: escape_html_tags(v) if isinstance(v, str) else v for k, v in kwargs.items()}
        return dm_translations.get(key, default_val).format(**escaped_kwargs)

    action = callback_query.data.split(":")[1]
    admin_user_id = callback_query.from_user.id
    config = await get_ai_config(supabase_client, group_id)
    if not config: config = {}

    if action == "toggle_cmd":
        current_status = config.get('ai_trigger_command_enabled', True)
        await save_ai_config(supabase_client, group_id, admin_user_id, trigger_command_enabled=not current_status)
    elif action == "toggle_mention":
        current_status = config.get('ai_trigger_mention_enabled', True)
        await save_ai_config(supabase_client, group_id, admin_user_id, trigger_mention_enabled=not current_status)
    elif action == "set_prefix":
        await callback_query.message.edit_text(get_dm_trigger_text("ask_custom_prefix_dm"))
        await callback_query.answer()
        return
    elif action == "remove_prefix":
        await save_ai_config(supabase_client, group_id, admin_user_id, trigger_custom_prefix="")
    elif action == "done":
        await callback_query.message.edit_text(get_dm_trigger_text("trigger_settings_updated"))
        await state.clear()
        await callback_query.answer()
        return

    if action in ["toggle_cmd", "toggle_mention", "remove_prefix"]:
        new_text, new_keyboard_markup = await build_triggers_menu(
            bot, supabase_client, group_id, raw_group_name, bot_username, lang_code_for_dm
        )
        try:
            await callback_query.message.edit_text(new_text, reply_markup=new_keyboard_markup)
        except Exception as e:
            if "message is not modified" in str(e).lower():
                logging.warning(f"Trigger menu edit: Message not modified. Group: {group_id}. Error: {e}")
                await callback_query.answer()
            else:
                logging.error(f"Error editing trigger menu: {e}")
    await callback_query.answer()

@admin_router.message(AISetupStates.awaiting_trigger_prefix, F.text)
async def process_trigger_prefix(message: types.Message, state: FSMContext, supabase_client: SupabaseClient, bot: Bot):
    fsm_data = await state.get_data()
    group_id = fsm_data.get("trigger_config_group_id")
    lang_code_for_dm = fsm_data.get("trigger_config_lang_code", DEFAULT_LANGUAGE)
    bot_username = fsm_data.get("trigger_config_bot_username", "YourBot")
    raw_group_name = fsm_data.get("trigger_config_group_name", "this group")
    admin_user_id = message.from_user.id

    if not group_id:
        await message.answer("Error: Session expired. Please use /set_ai_triggers in group again.")
        await state.clear()
        return

    dm_translations = load_translations(lang_code_for_dm)
    def get_dm_trigger_text(key, **kwargs):
        default_val = f"[{key}]"
        if 'default_text' in kwargs:
            default_val = kwargs.pop('default_text')
        escaped_kwargs = {k: escape_html_tags(v) if isinstance(v, str) else v for k, v in kwargs.items()}
        return dm_translations.get(key, default_val).format(**escaped_kwargs)

    prefix_input = message.text.strip()

    if prefix_input.lower() == "/remove_prefix_fsm":
        await save_ai_config(supabase_client, group_id, admin_user_id, trigger_custom_prefix="")
        await message.answer(get_dm_trigger_text("custom_prefix_removed_success_dm"))
    elif not prefix_input:
        await message.answer(get_dm_trigger_text("custom_prefix_empty_error_dm"))
        return
    elif prefix_input.startswith("/"):
        await message.answer(get_dm_trigger_text("custom_prefix_is_command_error_dm"))
        return
    else:
        await save_ai_config(supabase_client, group_id, admin_user_id, trigger_custom_prefix=prefix_input)
        await message.answer(get_dm_trigger_text("custom_prefix_set_success_dm", prefix=prefix_input))

    new_text, new_keyboard_markup = await build_triggers_menu(
        bot, supabase_client, group_id, raw_group_name, bot_username, lang_code_for_dm
    )
    await message.answer(new_text, reply_markup=new_keyboard_markup)
    await state.set_state(AISetupStates.awaiting_trigger_prefix)


@admin_router.message(Command("set_moderation"))
async def cmd_set_moderation(message: types.Message, state: FSMContext, supabase_client: SupabaseClient, _: callable, bot: Bot):
    if message.chat.type == 'private':
        await message.answer(_("command_only_in_group"))
        return
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.answer(_("admin_only_command"))
        return

    admin_user_id = message.from_user.id
    group_id = message.chat.id
    raw_group_name = message.chat.title or "this group"
    group_lang_for_dm = await get_group_language(supabase_client, group_id)

    storage = state.storage
    dm_key = StorageKey(bot_id=bot.id, chat_id=admin_user_id, user_id=admin_user_id)
    dm_fsm_context = FSMContext(storage=storage, key=dm_key)

    await dm_fsm_context.set_state(AISetupStates.awaiting_moderation_settings)
    await dm_fsm_context.update_data(
        moderation_config_group_id=group_id,
        moderation_config_lang_code=group_lang_for_dm,
        moderation_config_group_name=raw_group_name
    )

    text, keyboard = await build_moderation_menu(
        supabase_client, group_id, raw_group_name, group_lang_for_dm
    )
    try:
        await bot.send_message(admin_user_id, text, reply_markup=keyboard)
        await message.answer(_("moderation_config_sent_to_dm"))
    except Exception as e:
        logging.error(f"Error in cmd_set_moderation sending DM: {e}")
        await message.answer(_("dm_send_error_prompt"))


@admin_router.callback_query(StateFilter(AISetupStates.awaiting_moderation_settings), F.data.startswith(MODERATION_CALLBACK_PREFIX))
async def cq_moderation_settings_handler(callback_query: types.CallbackQuery, state: FSMContext, supabase_client: SupabaseClient, bot: Bot):
    fsm_data = await state.get_data()
    group_id = fsm_data.get("moderation_config_group_id")
    lang_code_for_dm = fsm_data.get("moderation_config_lang_code", DEFAULT_LANGUAGE)
    raw_group_name = fsm_data.get("moderation_config_group_name", "this group")
    admin_user_id = callback_query.from_user.id

    if not group_id:
        await callback_query.answer("Error: Session expired. Please use /set_moderation in group again.", show_alert=True)
        return

    dm_translations = load_translations(lang_code_for_dm)
    def get_dm_text(key, **kwargs):
        default_val = f"[{key}]"
        if 'default_text' in kwargs:
            default_val = kwargs.pop('default_text')
        escaped_kwargs = {k: escape_html_tags(v) if isinstance(v, str) else v for k, v in kwargs.items()}
        return dm_translations.get(key, default_val).format(**escaped_kwargs)

    action_full = callback_query.data.split(MODERATION_CALLBACK_PREFIX)[1]
    should_refresh_menu = False

    if action_full.startswith("setlevel_"):
        selected_level_code = action_full.split("_")[1]
        if selected_level_code in MODERATION_LEVELS:
            current_config_before_save = await get_ai_config(supabase_client, group_id)
            current_db_level = current_config_before_save.get('moderation_level', DEFAULT_MODERATION_LEVEL) if current_config_before_save else DEFAULT_MODERATION_LEVEL

            level_display_name_key = f"moderation_level_{selected_level_code}"
            level_display_name_default = MODERATION_LEVELS.get(selected_level_code, selected_level_code)
            selected_level_display_name = get_dm_text(level_display_name_key, default_text=level_display_name_default)

            if current_db_level == selected_level_code:
                await callback_query.answer(get_dm_text("moderation_level_already_set_dm", default_text="Moderation level is already set to {level}.", level=selected_level_display_name), show_alert=False)
                return

            success = await save_ai_config(supabase_client, group_id, admin_user_id, moderation_level=selected_level_code)
            if success:
                await callback_query.answer(get_dm_text("moderation_level_set_success_dm", group_name=raw_group_name, level=selected_level_display_name))
                should_refresh_menu = True
            else:
                await callback_query.answer(get_dm_text("generic_error"), show_alert=True)
        else:
            await callback_query.answer(get_dm_text("moderation_invalid_level_dm"), show_alert=True)

    elif action_full == "done":
        await callback_query.message.edit_text(get_dm_text("moderation_settings_updated_dm", group_name=raw_group_name))
        await state.clear()
        await callback_query.answer()
        return

    if should_refresh_menu:
        new_text, new_keyboard_markup = await build_moderation_menu(
            supabase_client, group_id, raw_group_name, lang_code_for_dm
        )
        try:
            await callback_query.message.edit_text(new_text, reply_markup=new_keyboard_markup)
        except Exception as e:
            if "message is not modified" in str(e).lower():
                logging.warning(f"Moderation menu edit: Message not modified. Group: {group_id}. Error: {e}")
                await callback_query.answer() # Still answer to remove loading
            else:
                logging.error(f"Error editing moderation menu: {e}")
    else:
        # Jika tidak ada refresh menu yang eksplisit, tetap jawab callback query
        # untuk menghilangkan status "loading" pada tombol.
        await callback_query.answer()


@admin_router.message(Command("cancel_setup"), StateFilter(AISetupStates.awaiting_moderation_settings))
async def cmd_cancel_moderation_setup_in_dm(message: types.Message, state: FSMContext, _: callable):
    logging.info(f"cmd_cancel_moderation_setup_in_dm: Cancelling setup for user {message.from_user.id}")
    fsm_data = await state.get_data()
    lang_code_for_dm = fsm_data.get("moderation_config_lang_code", DEFAULT_LANGUAGE)

    translations = load_translations(lang_code_for_dm)
    cancel_message_text = translations.get("setup_cancelled_dm", "Setup has been cancelled.")

    await state.clear()
    await message.answer(cancel_message_text)
    logging.info(f"cmd_cancel_moderation_setup_in_dm: State cleared.")
