import asyncio
import logging
import re
from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart, Command, ChatMemberUpdatedFilter, KICKED, MEMBER, LEFT, RESTRICTED
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.enums import ChatMemberStatus, ParseMode, ContentType
from supabase import Client as SupabaseClient
from bot_config import (
    AVAILABLE_LANGUAGES, DEFAULT_LANGUAGE, DEFAULT_GROQ_MODEL,
    PRIVACY_POLICY_URL, START_COMMAND_IMAGE_FILE_ID,
    MODERATION_LEVELS
)
from utils.supabase_interface import set_group_language, clear_conversation_history, get_group_language, get_ai_config
from utils.helpers import escape_html_tags
from utils.groq_interface import get_groq_completion
from utils.crypto_interface import CryptoUtil
from handlers.user_settings_handlers import USER_SETTINGS_CALLBACK_PREFIX
from middlewares.i18n_middleware import load_translations as load_specific_translations_common

common_router = Router()

HELP_CAT_PREFIX = "help_cat:"
HELP_CMD_PREFIX = "help_cmd:"

ADMIN_COMMANDS_HELP = [
    ("setup_ai", "help_btn_setup_ai"),
    ("get_ai_config", "help_btn_get_ai_config"),
    ("reset_ai_config", "help_btn_reset_ai_config"),
    ("set_language", "help_btn_set_language"),
    ("newchat", "help_btn_newchat"),
    ("set_ai_triggers", "help_btn_set_ai_triggers"),
    ("set_welcome", "help_btn_set_welcome"),
    ("set_moderation", "help_btn_set_moderation")
]

USER_COMMANDS_HELP = [
    ("help", "help_btn_help"),
    #("getinfoid", "help_btn_getinfoid")
]

AI_COMMANDS_HELP = [
    ("ask_ai", "help_btn_ask_ai"),
    ("mention_ai", "help_btn_mention_ai"),
    #("custom_prefix", "help_desc_custom_prefix_ai")
]

def get_help_main_menu_keyboard(_: callable):
    builder = InlineKeyboardBuilder()
    builder.button(text=_("button_help_admin_cmds"), callback_data=f"{HELP_CAT_PREFIX}admin")
    builder.button(text=_("button_help_user_cmds"), callback_data=f"{HELP_CAT_PREFIX}user")
    builder.button(text=_("button_help_ai_interaction"), callback_data=f"{HELP_CAT_PREFIX}ai")
    builder.adjust(1)
    return builder.as_markup()

def get_help_category_commands_keyboard(_: callable, commands_list: list, category_name: str, width: int = 2):
    builder = InlineKeyboardBuilder()
    buttons_in_row = []
    for cmd_key, button_locale_key in commands_list:
        display_text = _(button_locale_key)
        buttons_in_row.append(
            types.InlineKeyboardButton(text=display_text, callback_data=f"{HELP_CMD_PREFIX}{category_name}:{cmd_key}")
        )
    builder.row(*buttons_in_row, width=width)
    builder.row(types.InlineKeyboardButton(text=_("button_back_to_help_menu"), callback_data=f"{HELP_CAT_PREFIX}main"))
    return builder.as_markup()

def get_back_to_category_keyboard(_: callable, category_name: str):
    builder = InlineKeyboardBuilder()
    translated_category_title = ""
    if category_name == "admin": translated_category_title = _("button_help_admin_cmds")
    elif category_name == "user": translated_category_title = _("button_help_user_cmds")
    elif category_name == "ai": translated_category_title = _("button_help_ai_interaction")
    else: translated_category_title = category_name.capitalize()
    builder.button(text=_("button_back_to_category_cmds", category_name_display=translated_category_title), callback_data=f"{HELP_CAT_PREFIX}{category_name}")
    builder.button(text=_("button_back_to_help_menu"), callback_data=f"{HELP_CAT_PREFIX}main")
    builder.adjust(1)
    return builder.as_markup()

@common_router.message(Command("getinfoid"), F.chat.type.in_({'group', 'supergroup'}))
async def cmd_get_info_id(message: types.Message, _: callable):
    chat_id = message.chat.id
    chat_title = message.chat.title if message.chat.title else _("unknown_group_title")
    user_id = message.from_user.id

    message_thread_id = None
    topic_info_source_text = ""

    if message.reply_to_message and hasattr(message.reply_to_message, 'message_thread_id') and message.reply_to_message.message_thread_id:
        message_thread_id = message.reply_to_message.message_thread_id
        topic_info_source_text = _("getinfoid_topic_from_reply_source")
    elif message.is_topic_message and hasattr(message, 'message_thread_id') and message.message_thread_id:
        message_thread_id = message.message_thread_id
        topic_info_source_text = _("getinfoid_topic_from_current_source")

    response_parts = [
        _("getinfoid_response_header"),
        _("getinfoid_group_id", group_id=f"<code>{chat_id}</code>"),
        _("getinfoid_group_title", group_title=escape_html_tags(chat_title))
    ]

    if message_thread_id:
        response_parts.append(_("getinfoid_topic_id", topic_id=f"<code>{message_thread_id}</code>", source=topic_info_source_text))
    else:
        response_parts.append(_("getinfoid_no_topic_id_detected"))

    response_parts.append(_("getinfoid_user_id", user_id=f"<code>{user_id}</code>"))
    response_parts.append(_("getinfoid_usage_tip_for_sendmsg"))

    await message.reply("\n".join(response_parts), parse_mode=ParseMode.HTML)


@common_router.message(CommandStart())
async def handle_start(message: types.Message, _: callable, lang_code: str, lang_name: str, bot: Bot):
    user_name = message.from_user.full_name
    safe_user_name = escape_html_tags(user_name)
    welcome_message_part1 = _("welcome_message_user", user_full_name=safe_user_name)
    welcome_message_part2 = _("start_command_reply_with_buttons")
    full_caption = f"{welcome_message_part1}\n\n{welcome_message_part2}"
    builder = InlineKeyboardBuilder()
    if message.chat.type == "private":
        bot_info = await bot.get_me()
        bot_username = bot_info.username
        add_to_group_url = f"https://t.me/{bot_username}?startgroup=true&admin=all"
        builder.button(text=_("button_add_to_group"), url=add_to_group_url)
    builder.button(text=_("button_help_short", default="❓ Help"), callback_data=f"{HELP_CAT_PREFIX}main")
    if PRIVACY_POLICY_URL and PRIVACY_POLICY_URL != "https://t.me/YourChannelOrChat/YourMessageID":
        builder.button(text=_("button_privacy_policy"), url=PRIVACY_POLICY_URL)
    if message.chat.type == "private":
        builder.button(text=_("button_settings"), callback_data="trigger_settings_dm")
    builder.adjust(1)
    reply_markup_value = builder.as_markup() if builder.buttons else None
    if START_COMMAND_IMAGE_FILE_ID:
        try:
            await bot.send_photo(
                chat_id=message.chat.id, photo=START_COMMAND_IMAGE_FILE_ID,
                caption=full_caption, parse_mode=ParseMode.HTML,
                reply_markup=reply_markup_value
            )
        except Exception as e:
            logging.error(f"Failed to send photo in /start: {e}. Sending text message instead.")
            await message.answer(full_caption, reply_markup=reply_markup_value, parse_mode=ParseMode.HTML)
    else:
        await message.answer(full_caption, reply_markup=reply_markup_value, parse_mode=ParseMode.HTML)

@common_router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED >> MEMBER))
async def bot_added_to_group(event: types.ChatMemberUpdated, _: callable, bot: Bot):
    chat_id = event.chat.id
    group_name = event.chat.title
    bot_info = await bot.get_me()
    default_translations = load_specific_translations_common(DEFAULT_LANGUAGE)
    message_text = default_translations.get("bot_added_to_group_message", "").format(
        bot_name=escape_html_tags(bot_info.full_name),
        group_name=escape_html_tags(group_name)
    )
    if message_text:
        try:
            await bot.send_message(chat_id, message_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logging.error(f"Failed to send 'bot added to group' message to {chat_id}: {e}")

@common_router.callback_query(F.data == "trigger_settings_dm")
async def cq_trigger_settings_from_start(callback_query: types.CallbackQuery, _: callable, supabase_client: SupabaseClient, bot: Bot):
    if callback_query.message.chat.type == "private":
        user_id = callback_query.from_user.id
        settings_builder = InlineKeyboardBuilder()
        settings_builder.button(text=_("button_change_language_settings"), callback_data=f"{USER_SETTINGS_CALLBACK_PREFIX}prompt_lang_change")
        settings_builder.adjust(1)
        message_text = _("settings_menu_title")
        reply_markup = settings_builder.as_markup()
        try:
            if callback_query.message.content_type == ContentType.PHOTO:
                await callback_query.message.edit_caption(caption=message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            else:
                await callback_query.message.edit_text(text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except Exception as e:
            logging.warning(f"Failed to edit message for settings from start button: {e}. Sending new message.")
            await bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    await callback_query.answer()

@common_router.message(Command("help"))
async def cmd_help(message: types.Message, _: callable):
    await message.answer(_("help_main_menu_title"), reply_markup=get_help_main_menu_keyboard(_), parse_mode=ParseMode.HTML)

@common_router.callback_query(F.data.startswith(HELP_CAT_PREFIX))
async def cq_help_category_navigation(callback_query: types.CallbackQuery, _: callable):
    category_name = callback_query.data.split(HELP_CAT_PREFIX)[1]
    message_text = ""
    keyboard_markup = None
    if category_name == "main":
        message_text = _("help_main_menu_title")
        keyboard_markup = get_help_main_menu_keyboard(_)
    elif category_name == "admin":
        message_text = _("button_help_admin_cmds")
        keyboard_markup = get_help_category_commands_keyboard(_, ADMIN_COMMANDS_HELP, "admin")
    elif category_name == "user":
        message_text = _("button_help_user_cmds")
        keyboard_markup = get_help_category_commands_keyboard(_, USER_COMMANDS_HELP, "user")
    elif category_name == "ai":
        message_text = _("button_help_ai_interaction") + "\n\n" + _("help_ai_interaction_text")
        keyboard_markup = get_help_category_commands_keyboard(_, AI_COMMANDS_HELP, "ai")
    else:
        message_text = _("help_main_menu_title")
        keyboard_markup = get_help_main_menu_keyboard(_)
        await callback_query.answer("Unknown category", show_alert=True)
        return
    try:
        if callback_query.message.content_type == ContentType.PHOTO:
            await callback_query.message.edit_caption(caption=message_text, reply_markup=keyboard_markup, parse_mode=ParseMode.HTML)
        elif callback_query.message.text:
             await callback_query.message.edit_text(text=message_text, reply_markup=keyboard_markup, parse_mode=ParseMode.HTML)
        else:
            logging.warning(f"Help navigation: Original message (ID: {callback_query.message.message_id}) is not a photo and has no text to edit. Sending new message.")
            await callback_query.message.answer(text=message_text, reply_markup=keyboard_markup, parse_mode=ParseMode.HTML)
            if callback_query.message.reply_markup:
                 await callback_query.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        if "message is not modified" in str(e).lower():
            logging.warning(f"Help menu edit: Message not modified. Category: {category_name}. Error: {e}")
        else:
            logging.error(f"Error editing help message: {e}. Original message content type: {callback_query.message.content_type}")
            try:
                await callback_query.message.answer(text=message_text, reply_markup=keyboard_markup, parse_mode=ParseMode.HTML)
            except Exception as e2:
                logging.error(f"Error sending new help message after edit failed: {e2}")
    await callback_query.answer()

@common_router.callback_query(F.data.startswith(HELP_CMD_PREFIX))
async def cq_show_command_help(callback_query: types.CallbackQuery, _: callable): # _ di sini adalah fungsi callable
    try:
        # Gunakan nama variabel yang berbeda agar tidak menimpa '_' callable
        prefix_val, category_name, command_key = callback_query.data.split(":", 2)
    except ValueError:
        logging.error(f"Error parsing help_cmd callback data: {callback_query.data}")
        await callback_query.answer(_("generic_error"), show_alert=True) # _ di sini masih callable
        return

    description_key = f"help_desc_{command_key}"
    command_description = _(description_key) # _ di sini harusnya masih callable

    if command_description == description_key: 
        if command_key == "set_moderation" and _("set_moderation_command_description") != "set_moderation_command_description":
            command_description = _("set_moderation_command_description")
        elif command_key == "getinfoid" and _("getinfoid_command_description") != "getinfoid_command_description":
             command_description = _("getinfoid_command_description")
        elif command_key.startswith("moderation_level_"):
             level_code_part = command_key.replace("moderation_level_", "")
             level_name = MODERATION_LEVELS.get(level_code_part, level_code_part.capitalize())
             command_description = f"Set moderation level to: <b>{level_name}</b>."
        else:
            command_description = _("help_desc_not_found", command=f"/{command_key}")

    keyboard_markup = get_back_to_category_keyboard(_, category_name) # _ di sini juga callable
    message_text = command_description
    try:
        if callback_query.message.content_type == ContentType.PHOTO:
            await callback_query.message.edit_caption(caption=message_text, reply_markup=keyboard_markup, parse_mode=ParseMode.HTML)
        elif callback_query.message.text:
            await callback_query.message.edit_text(text=message_text, reply_markup=keyboard_markup, parse_mode=ParseMode.HTML)
        else:
            logging.warning(f"Show command help: Original message (ID: {callback_query.message.message_id}) is not a photo and has no text to edit. Sending new message.")
            await callback_query.message.answer(text=message_text, reply_markup=keyboard_markup, parse_mode=ParseMode.HTML)
            if callback_query.message.reply_markup:
                 await callback_query.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        if "message is not modified" in str(e).lower():
            logging.warning(f"Command help edit: Message not modified for /{command_key}. Error: {e}")
        else:
            logging.error(f"Error editing command help message: {e}. Original message content type: {callback_query.message.content_type}")
            try:
                await callback_query.message.answer(text=message_text, reply_markup=keyboard_markup, parse_mode=ParseMode.HTML)
            except Exception as e2:
                logging.error(f"Error sending new command help message after edit failed: {e2}")
    await callback_query.answer()

@common_router.message(Command("set_language"))
async def cmd_set_language(message: types.Message, _: callable, supabase_client: SupabaseClient, state: FSMContext):
    if message.chat.type == 'private':
        await message.answer(_("command_only_in_group"))
        return
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    if not (member.status == ChatMemberStatus.ADMINISTRATOR or member.status == ChatMemberStatus.CREATOR):
        await message.answer(_("admin_only_command"))
        return
    current_lang_code_for_buttons = DEFAULT_LANGUAGE
    try:
        group_lang_response = await asyncio.to_thread(
            supabase_client.table("group_configs")
            .select("language_code")
            .eq("group_id", message.chat.id)
            .maybe_single()
            .execute
        )
        if group_lang_response.data and group_lang_response.data.get("language_code"):
             current_lang_code_for_buttons = group_lang_response.data.get("language_code")
    except Exception as e:
        print(f"Error fetching language for buttons, defaulting to '{DEFAULT_LANGUAGE}'. Group ID: {message.chat.id}. Error: {repr(e)}")
    builder = InlineKeyboardBuilder()
    for code, name in AVAILABLE_LANGUAGES.items():
        builder.button(text=f"{name} ({code})", callback_data=f"setlang_{code}")
    builder.adjust(1)
    await message.answer(_("select_language_prompt"), reply_markup=builder.as_markup())

@common_router.callback_query(F.data.startswith("setlang_"))
async def cq_set_language(callback_query: types.CallbackQuery, _: callable, supabase_client: SupabaseClient):
    if callback_query.message.chat.type == 'private':
        await callback_query.answer(_("command_only_in_group"), show_alert=True)
        return
    member = await callback_query.bot.get_chat_member(callback_query.message.chat.id, callback_query.from_user.id)
    if not (member.status == ChatMemberStatus.ADMINISTRATOR or member.status == ChatMemberStatus.CREATOR):
        await callback_query.answer(_("admin_only_command"), show_alert=True)
        return
    lang_code = callback_query.data.split("_")[1]
    group_id = callback_query.message.chat.id
    admin_user_id = callback_query.from_user.id
    if lang_code in AVAILABLE_LANGUAGES:
        success = await set_group_language(supabase_client, group_id, lang_code, admin_user_id)
        if success:
            new_translations = load_specific_translations_common(lang_code)
            def get_new_lang_text(key, **kwargs):
                return new_translations.get(key, f"[{key}]").format(**kwargs)
            await callback_query.message.edit_text(get_new_lang_text("language_set_success", language_name=AVAILABLE_LANGUAGES[lang_code]))
            await callback_query.answer()
        else:
            current_lang_code_for_error = DEFAULT_LANGUAGE
            try:
                group_lang_resp_err = await asyncio.to_thread(
                    supabase_client.table("group_configs")
                    .select("language_code")
                    .eq("group_id", group_id)
                    .maybe_single()
                    .execute
                )
                if group_lang_resp_err.data and group_lang_resp_err.data.get("language_code"):
                    current_lang_code_for_error = group_lang_resp_err.data.get("language_code")
            except Exception as e:
                 print(f"Error fetching language for error message, defaulting to '{DEFAULT_LANGUAGE}'. Group ID: {group_id}. Error: {repr(e)}")
            error_translations = load_specific_translations_common(current_lang_code_for_error)
            def get_error_text(key, **kwargs):
                 return error_translations.get(key, f"[{key}]").format(**kwargs)
            await callback_query.message.edit_text(get_error_text("language_set_fail", available_codes=", ".join(AVAILABLE_LANGUAGES.keys())))
            await callback_query.answer(get_error_text("generic_error"), show_alert=True)
    else:
        await callback_query.answer(_("invalid_language_code"), show_alert=True)

@common_router.message(Command("newchat"))
async def cmd_newchat(message: types.Message, supabase_client: SupabaseClient, _: callable):
    if message.chat.type == 'private':
        await message.answer(_("command_only_in_group"))
        return
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    if not (member.status == ChatMemberStatus.ADMINISTRATOR or member.status == ChatMemberStatus.CREATOR):
        await message.answer(_("admin_only_command"))
        return
    group_id = message.chat.id
    success = await clear_conversation_history(supabase_client, group_id)
    if success:
        await message.reply(_("conversation_history_cleared"))
    else:
        await message.reply(_("error_clearing_history"))

@common_router.chat_member(ChatMemberUpdatedFilter(member_status_changed=(KICKED | LEFT | RESTRICTED) >> MEMBER))
async def on_user_join(event: types.ChatMemberUpdated, supabase_client: SupabaseClient, bot: Bot, crypto_util: CryptoUtil, _: callable):
    group_id = event.chat.id
    new_user = event.new_chat_member.user
    chat_title = event.chat.title if event.chat.title else "this group"
    logging.info(f"ON_USER_JOIN: User {new_user.id} ({new_user.full_name}) joined group {group_id} ('{chat_title}'). Fetching config.")
    config = await get_ai_config(supabase_client, group_id)

    if not config:
        logging.info(f"ON_USER_JOIN: No config found for group {group_id}. Skipping welcome message.")
        return
    if not config.get('welcome_message_enabled', False):
        logging.info(f"ON_USER_JOIN: Welcome messages disabled for group {group_id}. Skipping.")
        return

    user_mention_html = f"<a href='tg://user?id={new_user.id}'>{escape_html_tags(new_user.full_name)}</a>"
    user_first_name = escape_html_tags(new_user.first_name)
    user_last_name = escape_html_tags(new_user.last_name) if new_user.last_name else ""
    user_full_name = escape_html_tags(new_user.full_name)
    safe_group_name = escape_html_tags(chat_title)
    formatted_message = ""

    default_ai_welcome_prompt_template = (
        f"You are a friendly greeter bot for a Telegram group named '{{{{group_name}}}}'. "
        f"A new user, {{{{user_full_name_placeholder}}}}, has just joined. "
        f"Craft a unique, warm, and welcoming message for them. "
        f"You MUST use ALL of the following placeholders in your response exactly as they are written: "
        f"{{{{user_mention}}}}, {{{{user_first_name}}}}, {{{{user_last_name}}}}, {{{{user_full_name}}}}, {{{{group_name}}}}. "
        f"Do not add any extra text before or after the welcome message itself. Only the welcome message. "
        f"Make the message concise and engaging. Example: 'Hey {{{{user_mention}}}}, welcome to {{{{group_name}}}}! So glad to have you, {{{{user_first_name}}}}!' "
    )

    if config.get('welcome_message_ai_enabled', False):
        logging.info(f"ON_USER_JOIN: AI welcome message enabled for group {group_id}. Generating message...")
        if not config.get("encrypted_groq_api_key") or not config.get("is_active"):
            logging.warning(f"ON_USER_JOIN: AI welcome is ON for group {group_id} but AI (Groq) is not configured or inactive. Falling back to manual if available.")
            if config.get('custom_welcome_message'):
                custom_message_template = config.get('custom_welcome_message')
                formatted_message = custom_message_template.replace("{{user_mention}}", user_mention_html)
                formatted_message = formatted_message.replace("{{user_first_name}}", user_first_name)
                formatted_message = formatted_message.replace("{{user_last_name}}", user_last_name)
                formatted_message = formatted_message.replace("{{user_full_name}}", user_full_name)
                formatted_message = formatted_message.replace("{{group_name}}", safe_group_name)
            else:
                logging.info(f"ON_USER_JOIN: No manual fallback for AI welcome in group {group_id}.")
                return
        else:
            decrypted_api_key = crypto_util.decrypt_data(config.get("encrypted_groq_api_key"))
            if not decrypted_api_key:
                logging.error(f"ON_USER_JOIN: Failed to decrypt API key for AI welcome message in group {group_id}.")
                return

            ai_system_prompt_template_db = config.get('ai_welcome_system_prompt')
            current_ai_system_prompt = default_ai_welcome_prompt_template
            if ai_system_prompt_template_db and ai_system_prompt_template_db.strip():
                current_ai_system_prompt = ai_system_prompt_template_db
                logging.info(f"ON_USER_JOIN: Using custom AI welcome prompt for group {group_id}.")
            else:
                logging.info(f"ON_USER_JOIN: Using default AI welcome prompt for group {group_id}.")

            final_ai_system_prompt = current_ai_system_prompt.replace("{{group_name}}", safe_group_name)
            final_ai_system_prompt = final_ai_system_prompt.replace("{{user_full_name_placeholder}}", user_full_name)

            welcome_ai_model_id = "gemma2-9b-it"
            logging.info(f"ON_USER_JOIN: Using model '{welcome_ai_model_id}' for AI welcome. System prompt: '{final_ai_system_prompt[:150]}...'")

            ai_user_prompt = "Generate a short and friendly welcome message now, using the required placeholders."
            try:
                ai_response_data = await get_groq_completion(
                    api_key=decrypted_api_key, model=welcome_ai_model_id,
                    system_prompt_for_call=final_ai_system_prompt, user_prompt_for_call=ai_user_prompt,
                    full_messages_list=[
                        {"role": "system", "content": final_ai_system_prompt},
                        {"role": "user", "content": ai_user_prompt}
                    ]
                )
                if ai_response_data and ai_response_data.get("main_response"):
                    ai_generated_template = ai_response_data.get("main_response").strip()
                    logging.info(f"ON_USER_JOIN: AI generated welcome template for group {group_id}: '{ai_generated_template}'")

                    temp_message = ai_generated_template.replace("{{user_mention}}", user_mention_html)
                    temp_message = temp_message.replace("{{user_first_name}}", user_first_name)
                    temp_message = temp_message.replace("{{user_last_name}}", user_last_name)
                    temp_message = temp_message.replace("{{user_full_name}}", user_full_name)
                    temp_message = temp_message.replace("{{group_name}}", safe_group_name)
                    formatted_message = temp_message
                    logging.info(f"ON_USER_JOIN: After AI placeholder replacement, message: '{formatted_message}'")
                else:
                    logging.error(f"ON_USER_JOIN: AI failed to generate welcome message for group {group_id}. Response: {ai_response_data}")
                    if config.get('custom_welcome_message'):
                        custom_message_template = config.get('custom_welcome_message')
                        formatted_message = custom_message_template.replace("{{user_mention}}", user_mention_html)
                        formatted_message = formatted_message.replace("{{user_first_name}}", user_first_name)
                        formatted_message = formatted_message.replace("{{user_last_name}}", user_last_name)
                        formatted_message = formatted_message.replace("{{user_full_name}}", user_full_name)
                        formatted_message = formatted_message.replace("{{group_name}}", safe_group_name)
                    else: return
            except Exception as e_ai:
                logging.error(f"ON_USER_JOIN: Exception during AI welcome generation for group {group_id}: {repr(e_ai)}")
                if config.get('custom_welcome_message'):
                    custom_message_template = config.get('custom_welcome_message')
                    formatted_message = custom_message_template.replace("{{user_mention}}", user_mention_html)
                    formatted_message = formatted_message.replace("{{user_first_name}}", user_first_name)
                    formatted_message = formatted_message.replace("{{user_last_name}}", user_last_name)
                    formatted_message = formatted_message.replace("{{user_full_name}}", user_full_name)
                    formatted_message = formatted_message.replace("{{group_name}}", safe_group_name)
                else: return
    elif config.get('custom_welcome_message'):
        logging.info(f"ON_USER_JOIN: Using manual custom welcome message for group {group_id}.")
        custom_message_template = config.get('custom_welcome_message')
        formatted_message = custom_message_template.replace("{{user_mention}}", user_mention_html)
        formatted_message = formatted_message.replace("{{user_first_name}}", user_first_name)
        formatted_message = formatted_message.replace("{{user_last_name}}", user_last_name)
        formatted_message = formatted_message.replace("{{user_full_name}}", user_full_name)
        formatted_message = formatted_message.replace("{{group_name}}", safe_group_name)
    else:
        logging.info(f"ON_USER_JOIN: No welcome message (manual or AI) configured or enabled to be sent for group {group_id}.")
        return

    if formatted_message and formatted_message.strip():
        logging.info(f"ON_USER_JOIN: Attempting to send welcome message to group {group_id}: '{formatted_message[:200]}...'")
        try:
            if "<think>" in formatted_message.lower() or "</think>" in formatted_message.lower():
                logging.warning(f"ON_USER_JOIN: Detected <think> tags in final welcome. Cleaning. Original: '{formatted_message}'")
                formatted_message = re.sub(r"<think>.*?</think>", "", formatted_message, flags=re.DOTALL | re.IGNORECASE).strip()
                logging.info(f"ON_USER_JOIN: After think tag removal: '{formatted_message}'")

            if formatted_message and formatted_message.strip():
                await bot.send_message(chat_id=group_id, text=formatted_message, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                logging.info(f"ON_USER_JOIN: Successfully sent welcome message to group {group_id}.")
            else:
                logging.warning(f"ON_USER_JOIN: Formatted welcome message became empty after all processing for group {group_id}. Not sending.")
        except Exception as e:
            logging.error(f"ON_USER_JOIN: Error sending welcome message to group {group_id}: {repr(e)}. Formatted message was: '{formatted_message}'")
    else:
        logging.warning(f"ON_USER_JOIN: Formatted_message was empty or None before attempting to send for group {group_id}.")


@common_router.message(F.photo)
async def get_photo_file_id(message: types.Message):
    if message.photo:
        largest_photo = message.photo[-1]
        file_id_to_copy = largest_photo.file_id
        await message.reply(
            f"Foto diterima!\n\n<b>File ID untuk disalin:</b>\n<code>{file_id_to_copy}</code>\n\n"
            f"Resolusi: {largest_photo.width}x{largest_photo.height}\n"
            f"Ukuran file: {largest_photo.file_size} bytes"
        )
        logging.info(f"PHOTO HANDLER: Received photo. File ID: {file_id_to_copy}")
