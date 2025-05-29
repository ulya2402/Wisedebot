import logging
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ChatMemberStatus
from supabase import Client as SupabaseClient
from states.setup_states import AISetupStates
from utils.supabase_interface import get_ai_config, save_ai_config, get_group_language
from utils.helpers import escape_html_tags
from bot_config import DEFAULT_LANGUAGE
from middlewares.i18n_middleware import load_translations as load_specific_translations

welcome_router = Router()

WELCOME_CALLBACK_PREFIX = "wm_cfg:"

async def is_admin_welcome(bot_instance: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot_instance.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        logging.error(f"Error checking admin status: {e}")
        return False


async def build_welcome_message_menu(
    bot_instance: Bot,
    supabase_client: SupabaseClient,
    group_id: int,
    raw_group_name_from_fsm: str,
    lang_code_for_dm: str
):
    current_dm_translations = load_specific_translations(lang_code_for_dm)
    def get_menu_text(key, **kwargs):
        escaped_kwargs = {k: escape_html_tags(v) if isinstance(v, str) else v for k, v in kwargs.items()}
        return current_dm_translations.get(key, f"[{key}]").format(**escaped_kwargs)

    config = await get_ai_config(supabase_client, group_id) #
    welcome_enabled = config.get('welcome_message_enabled', False) if config else False #
    custom_message = config.get('custom_welcome_message', '') if config else '' #
    ai_welcome_enabled = config.get('welcome_message_ai_enabled', False) if config else False

    status_text = get_menu_text("welcome_status_enabled") if welcome_enabled else get_menu_text("welcome_status_disabled") #
    message_display_text = custom_message if custom_message else get_menu_text("welcome_message_not_set_status_dm") #

    ai_status_text = get_menu_text("welcome_status_enabled") if ai_welcome_enabled else get_menu_text("welcome_status_disabled")

    menu_text = get_menu_text("welcome_message_menu_title_dm", group_name=raw_group_name_from_fsm) + "\n\n" #
    menu_text += get_menu_text("welcome_message_current_status_dm", status=status_text, message_text=escape_html_tags(message_display_text)) #
    menu_text += "\n" + get_menu_text("welcome_ai_status_header_dm", ai_status=ai_status_text)


    builder = InlineKeyboardBuilder() #
    if welcome_enabled: #
        builder.button(
            text=get_menu_text("button_disable_welcome_dm"), #
            callback_data=f"{WELCOME_CALLBACK_PREFIX}disable" #
        )
    else:
        builder.button(
            text=get_menu_text("button_enable_welcome_dm"), #
            callback_data=f"{WELCOME_CALLBACK_PREFIX}enable" #
        )

    # Tombol untuk mode AI
    if ai_welcome_enabled:
        builder.button(
            text=get_menu_text("button_toggle_welcome_ai_dm_disable"), # Menggunakan kunci baru
            callback_data=f"{WELCOME_CALLBACK_PREFIX}toggle_ai"
        )
    else:
        builder.button(
            text=get_menu_text("button_toggle_welcome_ai_dm_enable"), # Menggunakan kunci baru
            callback_data=f"{WELCOME_CALLBACK_PREFIX}toggle_ai"
        )

    # Tombol untuk pesan manual hanya muncul jika mode AI tidak aktif
    if not ai_welcome_enabled:
        builder.button(
            text=get_menu_text("button_set_custom_welcome_dm"), #
            callback_data=f"{WELCOME_CALLBACK_PREFIX}prompt_set" #
        )
        if custom_message: #
            builder.button(
                text=get_menu_text("button_remove_custom_welcome_dm"), #
                callback_data=f"{WELCOME_CALLBACK_PREFIX}remove" #
            )

    builder.button(
        text=get_menu_text("button_done_triggers"), #
        callback_data=f"{WELCOME_CALLBACK_PREFIX}done" #
    )

    # Penyesuaian layout tombol
    if not ai_welcome_enabled:
        builder.adjust(1, 1, 2 if custom_message else 1, 1) #
    else:
        builder.adjust(1, 1, 1) # Hanya tombol enable/disable welcome, tombol AI, dan tombol Done

    return menu_text, builder.as_markup()

@welcome_router.message(Command("set_welcome"))
async def cmd_set_welcome(message: types.Message, state: FSMContext, supabase_client: SupabaseClient, _: callable, bot: Bot): #
    logging.info(f"cmd_set_welcome triggered by user {message.from_user.id} in chat {message.chat.id}") #
    if message.chat.type == 'private': #
        logging.info("cmd_set_welcome: Command used in private chat. Replying and returning.") #
        await message.answer(_("command_only_in_group")) #
        return

    is_admin = await is_admin_welcome(bot, message.chat.id, message.from_user.id) #
    logging.info(f"cmd_set_welcome: User is admin: {is_admin}") #
    if not is_admin: #
        logging.info("cmd_set_welcome: User is not admin. Replying and returning.") #
        await message.answer(_("admin_only_command")) #
        return

    admin_user_id = message.from_user.id #
    group_id = message.chat.id #
    raw_group_name = message.chat.title or "this group" #
    logging.info(f"cmd_set_welcome: Group ID: {group_id}, Group Name: {raw_group_name}, Admin ID: {admin_user_id}") #

    group_lang_for_dm = await get_group_language(supabase_client, group_id) #
    if not group_lang_for_dm: #
        group_lang_for_dm = DEFAULT_LANGUAGE #
    logging.info(f"cmd_set_welcome: Language for DM: {group_lang_for_dm}") #


    storage = state.storage #
    dm_key = StorageKey(bot_id=bot.id, chat_id=admin_user_id, user_id=admin_user_id) #
    dm_fsm_context = FSMContext(storage=storage, key=dm_key) #
    logging.info(f"cmd_set_welcome: DM FSM Key created: {dm_key}") #

    await dm_fsm_context.set_state(AISetupStates.awaiting_welcome_message_status) #
    await dm_fsm_context.update_data( #
        welcome_config_group_id=group_id, #
        welcome_config_lang_code=group_lang_for_dm, #
        welcome_config_group_name=raw_group_name #
    )
    logging.info(f"cmd_set_welcome: DM FSM state set to awaiting_welcome_message_status and data updated.") #
    current_fsm_data = await dm_fsm_context.get_data() #
    logging.info(f"cmd_set_welcome: Current DM FSM data: {current_fsm_data}") #


    menu_text, keyboard = await build_welcome_message_menu( #
        bot, supabase_client, group_id, raw_group_name, group_lang_for_dm
    )
    logging.info(f"cmd_set_welcome: Welcome menu built. Attempting to send DM.") #

    try:
        await bot.send_message(admin_user_id, menu_text, reply_markup=keyboard) #
        logging.info(f"cmd_set_welcome: DM sent successfully to admin {admin_user_id}.") #
        await message.answer(_("welcome_config_sent_to_dm")) #
    except Exception as e:
        logging.error(f"Error cmd_set_welcome sending DM: {repr(e)}") #
        await message.answer(_("dm_send_error_prompt")) #


@welcome_router.callback_query(StateFilter(AISetupStates.awaiting_welcome_message_status), F.data.startswith(WELCOME_CALLBACK_PREFIX))
async def cq_welcome_message_handler(callback_query: types.CallbackQuery, state: FSMContext, supabase_client: SupabaseClient, bot: Bot): #
    fsm_data = await state.get_data() #
    logging.info(f"cq_welcome_message_handler: FSM data (DM context): {fsm_data}") #
    group_id = fsm_data.get("welcome_config_group_id") #
    lang_code_for_dm = fsm_data.get("welcome_config_lang_code", DEFAULT_LANGUAGE) #
    raw_group_name = fsm_data.get("welcome_config_group_name", "this group") #
    admin_user_id = callback_query.from_user.id #

    if not group_id: #
        dm_translations_error = load_specific_translations(lang_code_for_dm) #
        logging.error(f"cq_welcome_message_handler: group_id not found in FSM data.") #
        await callback_query.answer(dm_translations_error.get("generic_error", "Error: Session expired.") + " (Group ID missing)", show_alert=True) #
        return

    current_dm_translations = load_specific_translations(lang_code_for_dm) #
    def get_dm_text(key, **kwargs): #
        escaped_kwargs = {k: escape_html_tags(v) if isinstance(v, str) else v for k, v in kwargs.items()} #
        return current_dm_translations.get(key, f"[{key}]").format(**escaped_kwargs) #

    action = callback_query.data.split(WELCOME_CALLBACK_PREFIX)[1] #
    logging.info(f"cq_welcome_message_handler: Processing action '{action}' for group {group_id}") #
    success = False #

    if action == "enable": #
        success = await save_ai_config(supabase_client, group_id, admin_user_id, welcome_message_enabled=True) #
        if success: await callback_query.answer(get_dm_text("welcome_message_enabled_success_dm", group_name=raw_group_name)) #
    elif action == "disable": #
        success = await save_ai_config(supabase_client, group_id, admin_user_id, welcome_message_enabled=False) #
        if success: await callback_query.answer(get_dm_text("welcome_message_disabled_success_dm", group_name=raw_group_name)) #
    elif action == "toggle_ai":
        config = await get_ai_config(supabase_client, group_id) #
        current_ai_status = config.get('welcome_message_ai_enabled', False) if config else False
        new_ai_status = not current_ai_status
        success = await save_ai_config(supabase_client, group_id, admin_user_id, welcome_message_ai_enabled=new_ai_status)
        if success:
            if new_ai_status:
                await callback_query.answer(get_dm_text("welcome_message_ai_enabled_success_dm", group_name=raw_group_name))
            else:
                await callback_query.answer(get_dm_text("welcome_message_ai_disabled_success_dm", group_name=raw_group_name))
    elif action == "prompt_set": #
        config = await get_ai_config(supabase_client, group_id) #
        ai_welcome_enabled = config.get('welcome_message_ai_enabled', False) if config else False
        if ai_welcome_enabled:
            await callback_query.answer("AI welcome message is active. Disable it to set a manual message.", show_alert=True)
            return # Jangan lanjutkan ke pengaturan pesan manual jika AI aktif

        await state.set_state(AISetupStates.awaiting_custom_welcome_message) #
        prompt_text = get_dm_text("prompt_enter_welcome_message_dm") #
        await callback_query.message.edit_text(prompt_text) #
        await callback_query.answer() #
        logging.info(f"cq_welcome_message_handler: State set to awaiting_custom_welcome_message. Prompt sent.") #
        return
    elif action == "remove": #
        config = await get_ai_config(supabase_client, group_id) #
        if config and config.get('custom_welcome_message'): #
            success = await save_ai_config(supabase_client, group_id, admin_user_id, custom_welcome_message="") #
            if success: await callback_query.answer(get_dm_text("welcome_message_removed_success_dm", group_name=raw_group_name)) #
        else:
            await callback_query.answer(get_dm_text("no_welcome_message_to_remove_dm"), show_alert=True) #
            return
    elif action == "done": #
        await callback_query.message.edit_text(get_dm_text("trigger_settings_updated")) #
        await state.clear() #
        await callback_query.answer() #
        logging.info(f"cq_welcome_message_handler: Action 'done'. State cleared.") #
        return

    if not success and action in ["enable", "disable", "remove", "toggle_ai"]: #
        logging.error(f"cq_welcome_message_handler: Save operation failed for action '{action}'.") #
        await callback_query.answer(get_dm_text("generic_error"), show_alert=True) #

    if action in ["enable", "disable", "remove", "toggle_ai"] and success: #
        logging.info(f"cq_welcome_message_handler: Refreshing menu for action '{action}'.") #
        new_menu_text, new_keyboard = await build_welcome_message_menu( #
            bot, supabase_client, group_id, raw_group_name, lang_code_for_dm
        )
        try:
            await callback_query.message.edit_text(new_menu_text, reply_markup=new_keyboard) #
        except Exception as e:
            logging.error(f"Error refreshing welcome menu: {repr(e)}") #
            pass


@welcome_router.message(AISetupStates.awaiting_custom_welcome_message, F.text)
async def process_custom_welcome_message(message: types.Message, state: FSMContext, supabase_client: SupabaseClient, bot: Bot): #
    fsm_data = await state.get_data() #
    logging.info(f"process_custom_welcome_message: FSM data: {fsm_data}") #
    group_id = fsm_data.get("welcome_config_group_id") #
    lang_code_for_dm = fsm_data.get("welcome_config_lang_code", DEFAULT_LANGUAGE) #
    raw_group_name = fsm_data.get("welcome_config_group_name", "this group") #
    admin_user_id = message.from_user.id #

    current_dm_translations = load_specific_translations(lang_code_for_dm) #
    def get_dm_text(key, **kwargs): #
        escaped_kwargs = {k: escape_html_tags(v) if isinstance(v, str) else v for k, v in kwargs.items()} #
        return current_dm_translations.get(key, f"[{key}]").format(**escaped_kwargs) #

    if not group_id: #
        logging.error(f"process_custom_welcome_message: group_id not found in FSM data.") #
        await message.answer(get_dm_text("generic_error") + " (Group ID missing in state)") #
        await state.clear() #
        return

    custom_message_text = message.text.strip() #
    if not custom_message_text: #
        logging.info(f"process_custom_welcome_message: Empty custom message received.") #
        await message.answer(get_dm_text("welcome_message_empty_error_dm")) #
        prompt_text = get_dm_text("prompt_enter_welcome_message_dm") #
        await message.answer(prompt_text) #
        return

    logging.info(f"process_custom_welcome_message: Saving custom message: '{custom_message_text}' for group {group_id}") #
    success = await save_ai_config(supabase_client, group_id, admin_user_id, custom_welcome_message=custom_message_text) #

    if success: #
        logging.info(f"process_custom_welcome_message: Custom message saved successfully.") #
        await message.answer(get_dm_text("welcome_message_set_success_dm", group_name=raw_group_name, message_text=escape_html_tags(custom_message_text))) #
        await state.set_state(AISetupStates.awaiting_welcome_message_status) #
        logging.info(f"process_custom_welcome_message: State set back to awaiting_welcome_message_status.") #
        menu_text, keyboard = await build_welcome_message_menu( #
            bot, supabase_client, group_id, raw_group_name, lang_code_for_dm
        )
        await message.answer(menu_text, reply_markup=keyboard) #
    else:
        logging.error(f"process_custom_welcome_message: Failed to save custom message.") #
        await message.answer(get_dm_text("generic_error")) #
        prompt_text = get_dm_text("prompt_enter_welcome_message_dm") #
        await message.answer(prompt_text) #

@welcome_router.message(Command("cancel_setup"), StateFilter(AISetupStates.awaiting_welcome_message_status, AISetupStates.awaiting_custom_welcome_message))
async def cmd_cancel_welcome_setup_in_dm(message: types.Message, state: FSMContext, _: callable): #
    logging.info(f"cmd_cancel_welcome_setup_in_dm: Cancelling setup for user {message.from_user.id}") #
    fsm_data = await state.get_data() #
    lang_code_for_dm = fsm_data.get("welcome_config_lang_code", DEFAULT_LANGUAGE) #

    translations = load_specific_translations(lang_code_for_dm) #
    cancel_message_text = translations.get("setup_cancelled_dm", "Setup has been cancelled.") #

    await state.clear() #
    await message.answer(cancel_message_text) #
    logging.info(f"cmd_cancel_welcome_setup_in_dm: State cleared.") #

@welcome_router.message(AISetupStates.awaiting_custom_welcome_message, ~F.text)
async def process_non_text_for_welcome_message(message: types.Message, state: FSMContext, _: callable): #
    logging.info(f"process_non_text_for_welcome_message: Non-text message received in awaiting_custom_welcome_message state.") #
    fsm_data = await state.get_data() #
    lang_code_for_dm = fsm_data.get("welcome_config_lang_code", DEFAULT_LANGUAGE) #
    translations = load_specific_translations(lang_code_for_dm) #
    await message.answer(translations.get("fsm_expecting_text_prompt", "I'm expecting text input here.")) #
