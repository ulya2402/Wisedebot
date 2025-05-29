from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder
from supabase import Client as SupabaseClient
from states.setup_states import AISetupStates
from utils.supabase_interface import save_ai_config, get_group_language 
from utils.groq_interface import validate_groq_api_key
from utils.crypto_interface import CryptoUtil
from bot_config import DEFAULT_GROQ_MODEL, DEFAULT_LANGUAGE, AVAILABLE_GROQ_MODELS, get_model_display_name
from utils.helpers import escape_html_tags 

fsm_router = Router()

MODEL_CALLBACK_PREFIX = "select_model:"

@fsm_router.message(Command("cancel_setup"), StateFilter(AISetupStates))
async def cmd_cancel_setup(message: types.Message, state: FSMContext, _: callable):
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.clear()
    await message.answer(_("setup_cancelled_dm"))

@fsm_router.message(AISetupStates.awaiting_groq_key, F.text)
async def process_groq_key(message: types.Message, state: FSMContext, _: callable):
    groq_api_key = message.text.strip()
    if not groq_api_key.startswith("gsk_"):
        builder = InlineKeyboardBuilder()
        builder.button(text=_("button_get_groq_api_key"), url="https://console.groq.com/keys")
        await message.answer(_("invalid_api_key_format_dm"), reply_markup=builder.as_markup(resize_keyboard=True))
        return

    await message.answer(_("api_key_validation_checking_dm"))
    is_valid, error_details = await validate_groq_api_key(groq_api_key)

    if not is_valid:
        builder = InlineKeyboardBuilder()
        builder.button(text=_("button_get_groq_api_key"), url="https://console.groq.com/keys")
        error_msg_key = "api_key_validation_failed_with_groq_dm"
        error_text = _(error_msg_key, error_details=escape_html_tags(error_details or "Unknown validation error"))
        await message.answer(error_text, reply_markup=builder.as_markup(resize_keyboard=True))
        return

    await state.update_data(groq_api_key=groq_api_key) # Menyimpan dengan key 'groq_api_key'
    await message.answer(_("api_key_validation_successful_dm"))
    await message.answer(_("request_system_prompt_dm")) # String ini sederhana sekarang
    await state.set_state(AISetupStates.awaiting_system_prompt)

@fsm_router.message(AISetupStates.awaiting_system_prompt, F.text)
async def process_system_prompt(message: types.Message, state: FSMContext, _: callable):
    system_prompt = message.text.strip()
    # Pastikan system_prompt tidak hanya spasi kosong
    if not system_prompt:
        await message.answer(_("system_prompt_cannot_be_empty")) # Tambahkan key ini ke locale: "System prompt cannot be empty. Please provide a valid prompt or type /cancel_setup."
        return

    await state.update_data(system_prompt=system_prompt) # Menyimpan dengan key 'system_prompt'

    default_model_id = DEFAULT_GROQ_MODEL
    default_model_display_name = get_model_display_name(default_model_id)
    escaped_default_model_display = escape_html_tags(default_model_display_name)

    model_buttons = InlineKeyboardBuilder()
    for model_info in AVAILABLE_GROQ_MODELS:
        model_buttons.button(
            text=model_info["display_name"], 
            callback_data=f"{MODEL_CALLBACK_PREFIX}{model_info['id']}"
        )
    model_buttons.adjust(1)

    await message.answer(
        _("request_groq_model_dm", default_model=escaped_default_model_display),
        reply_markup=model_buttons.as_markup()
    )
    await state.set_state(AISetupStates.awaiting_groq_model)

@fsm_router.callback_query(AISetupStates.awaiting_groq_model, F.data.startswith(MODEL_CALLBACK_PREFIX))
async def select_groq_model(callback_query: types.CallbackQuery, state: FSMContext, _: callable):
    selected_model_id = callback_query.data.split(MODEL_CALLBACK_PREFIX)[1]

    await state.update_data(groq_model_id=selected_model_id) # Menyimpan dengan key 'groq_model_id'

    data = await state.get_data()
    raw_group_name = data.get("group_name_to_configure", "this group")
    safe_group_name = escape_html_tags(raw_group_name)

    raw_api_key = data.get("groq_api_key", "")
    api_key_to_display = raw_api_key[:7] + "****" if raw_api_key else _("not_set")
    safe_api_key_display = escape_html_tags(api_key_to_display)

    raw_prompt_from_data = data.get("system_prompt", _("not_set"))
    safe_prompt_display = escape_html_tags(raw_prompt_from_data)

    model_id_for_confirmation = data.get("groq_model_id", DEFAULT_GROQ_MODEL) # Mengambil 'groq_model_id'
    display_name_for_confirmation = get_model_display_name(model_id_for_confirmation)
    safe_model_display_confirmation = escape_html_tags(display_name_for_confirmation)

    text = _("confirm_setup_details_title_dm", group_name=safe_group_name) + "\n"
    text += _("confirm_setup_api_key_masked_dm", masked_api_key=safe_api_key_display) + "\n"
    text += _("confirm_setup_system_prompt_dm", system_prompt=safe_prompt_display) + "\n"
    text += _("confirm_setup_groq_model_dm", groq_model=safe_model_display_confirmation) + "\n\n"
    text += _("confirm_setup_save_prompt_dm")

    builder = InlineKeyboardBuilder()
    builder.button(text=_("button_yes_save_config_dm"), callback_data="fsm_save_config")
    builder.button(text=_("button_edit_config_dm"), callback_data="fsm_edit_config")
    builder.button(text=_("button_cancel_setup_dm"), callback_data="fsm_cancel_setup")
    builder.adjust(1)

    await callback_query.message.edit_text(text, reply_markup=builder.as_markup())
    await state.set_state(AISetupStates.confirm_ai_setup)
    await callback_query.answer()


@fsm_router.callback_query(AISetupStates.confirm_ai_setup, F.data == "fsm_save_config")
async def cq_fsm_save_config(callback_query: types.CallbackQuery, state: FSMContext, supabase_client: SupabaseClient, crypto_util: CryptoUtil, _: callable):
    data = await state.get_data()

    print("--- FSM Data before saving config ---")
    print(f"Raw FSM data: {data}")

    group_id = data.get("group_id_to_configure")
    plain_groq_api_key = data.get("groq_api_key")
    system_prompt = data.get("system_prompt")
    groq_model_id_to_save = data.get("groq_model_id") # Mengambil dengan key 'groq_model_id'

    print(f"Extracted group_id: {group_id}")
    print(f"Extracted plain_groq_api_key: {plain_groq_api_key}")
    print(f"Extracted system_prompt: {system_prompt}")
    print(f"Extracted groq_model_id_to_save: {groq_model_id_to_save}")
    print("--- End FSM Data debug ---")

    admin_user_id = callback_query.from_user.id 
    raw_group_name = data.get("group_name_to_configure", "N/A")
    lang_code = data.get("lang_code", DEFAULT_LANGUAGE) 

    # Validasi semua data sebelum melanjutkan
    # Kita juga bisa menambahkan pengecekan apakah string hanya spasi di sini jika perlu
    all_data_present = True
    if not group_id: 
        print("DEBUG: group_id is missing or falsey")
        all_data_present = False
    if not plain_groq_api_key: 
        print("DEBUG: plain_groq_api_key is missing or falsey")
        all_data_present = False
    if not system_prompt: 
        print("DEBUG: system_prompt is missing or falsey")
        all_data_present = False
    if not groq_model_id_to_save: 
        print("DEBUG: groq_model_id_to_save is missing or falsey")
        all_data_present = False

    if not all_data_present: # Menggunakan variabel baru untuk kejelasan
        await callback_query.message.edit_text(_("generic_error") + " (Missing data in FSM state. Please try setup again.)")
        await state.clear()
        await callback_query.answer(_("generic_error"), show_alert=True)
        return

    encrypted_groq_api_key = crypto_util.encrypt_data(plain_groq_api_key)
    if not encrypted_groq_api_key:
        await callback_query.message.edit_text(_("generic_error") + " (Encryption failed)")
        await state.clear()
        await callback_query.answer(_("generic_error"), show_alert=True)
        return

    success = await save_ai_config(
        supabase_client, 
        group_id, 
        admin_user_id, 
        encrypted_groq_api_key, 
        system_prompt, 
        groq_model_id_to_save, 
        lang_code
    )

    if success:
        safe_group_name_for_dm = escape_html_tags(raw_group_name)
        await callback_query.message.edit_text(_("config_saved_success_dm", group_name=safe_group_name_for_dm))
        try: 
            group_actual_lang = await get_group_language(supabase_client, group_id) 
            from middlewares.i18n_middleware import load_translations
            group_translations = load_translations(group_actual_lang)
            def get_group_notif_text(key): 
                return group_translations.get(key, f"[{key}]")

            await callback_query.bot.send_message(group_id, get_group_notif_text("config_updated_group_notification"))
        except Exception as e:
            print(f"Failed to send setup completion notification to group {group_id}: {repr(e)}")
    else:
        await callback_query.message.edit_text(_("generic_error") + " (Failed to save to DB)")

    await state.clear()
    await callback_query.answer()

@fsm_router.callback_query(AISetupStates.confirm_ai_setup, F.data == "fsm_edit_config")
async def cq_fsm_edit_config(callback_query: types.CallbackQuery, state: FSMContext, _: callable):
    fsm_data = await state.get_data()
    lang_code = fsm_data.get("lang_code", DEFAULT_LANGUAGE)

    from middlewares.i18n_middleware import load_translations
    dm_translations = load_translations(lang_code)
    def get_dm_text_local(key): 
        return dm_translations.get(key, f"[{key}]")

    builder = InlineKeyboardBuilder()
    builder.button(text=get_dm_text_local("button_get_groq_api_key"), url="https://console.groq.com/keys")
    await callback_query.message.edit_text(
        get_dm_text_local("request_groq_key_dm"), 
        reply_markup=builder.as_markup(resize_keyboard=True)
    )
    await state.set_state(AISetupStates.awaiting_groq_key)
    await callback_query.answer()

@fsm_router.callback_query(AISetupStates.confirm_ai_setup, F.data == "fsm_cancel_setup")
async def cq_fsm_cancel_setup(callback_query: types.CallbackQuery, state: FSMContext, _: callable):
    await state.clear()
    await callback_query.message.edit_text(_("setup_cancelled_dm"))
    await callback_query.answer()

@fsm_router.message(AISetupStates.awaiting_groq_key, ~F.text)
@fsm_router.message(AISetupStates.awaiting_system_prompt, ~F.text)
@fsm_router.message(AISetupStates.awaiting_groq_model, F.text) 
async def process_text_when_expecting_model_button_or_invalid_type(message: types.Message, state: FSMContext, _: callable):
    current_state = await state.get_state()
    if current_state == AISetupStates.awaiting_groq_model:
        fsm_data = await state.get_data()
        default_model_id = DEFAULT_GROQ_MODEL
        default_model_display_name = get_model_display_name(default_model_id)
        escaped_default_model = escape_html_tags(default_model_display_name)

        model_buttons = InlineKeyboardBuilder()
        for model_info in AVAILABLE_GROQ_MODELS:
            model_buttons.button(text=model_info["display_name"], callback_data=f"{MODEL_CALLBACK_PREFIX}{model_info['id']}")
        model_buttons.adjust(1)

        # Anda perlu menambahkan key "please_select_from_buttons" ke file locale Anda
        # Contoh en.json: "please_select_from_buttons": "Please select a model using the buttons above."
        await message.answer(
             _("request_groq_model_dm", default_model=escaped_default_model) + "\n\n" + _("please_select_from_buttons"),
            reply_markup=model_buttons.as_markup()
        )
    else: 
        await message.answer(_("fsm_expecting_text_prompt"))

@fsm_router.message(AISetupStates.awaiting_groq_model, ~F.text)
async def process_non_text_in_model_state(message: types.Message, _: callable):
     # Anda perlu menambahkan key "fsm_expecting_button_click_prompt" ke file locale Anda
     # Contoh en.json: "fsm_expecting_button_click_prompt": "Please click one of the model buttons above, or type /cancel_setup."
     await message.answer(_("fsm_expecting_button_click_prompt"))
