import logging
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from supabase import Client as SupabaseClient
from aiogram.enums import ContentType, ParseMode 
from bot_config import AVAILABLE_LANGUAGES, DEFAULT_LANGUAGE
from utils.supabase_interface import set_user_language, get_user_language
from middlewares.i18n_middleware import load_translations

USER_SETTINGS_CALLBACK_PREFIX = "userset:"

user_settings_router = Router()

async def get_language_selection_keyboard(user_id: int, supabase_client: SupabaseClient, current_lang_for_buttons: str) -> InlineKeyboardBuilder:
    lang_for_button_text = current_lang_for_buttons
    translations_for_buttons = load_translations(lang_for_button_text)

    def get_btn_text(key, **kwargs):
        return translations_for_buttons.get(key, f"[{key}]").format(**kwargs)

    builder = InlineKeyboardBuilder()
    current_user_lang = await get_user_language(supabase_client, user_id)

    for code, name in AVAILABLE_LANGUAGES.items():
        button_text = f"{name} ({code})"
        if current_user_lang == code:
            button_text = f"✅ {button_text} ({get_btn_text('current_language_indicator')})"
        builder.button(text=button_text, callback_data=f"{USER_SETTINGS_CALLBACK_PREFIX}setlang_{code}")

    builder.button(text=get_btn_text("button_back_to_settings_menu"), callback_data=f"{USER_SETTINGS_CALLBACK_PREFIX}main")
    builder.adjust(1)
    return builder

@user_settings_router.message(Command("settings"))
async def cmd_settings(message: types.Message, _: callable, supabase_client: SupabaseClient):
    if message.chat.type != "private": #
        await message.reply(_("command_only_in_dm_settings")) 
        return

    user_id = message.from_user.id

    builder = InlineKeyboardBuilder()
    builder.button(text=_("button_change_language_settings"), callback_data=f"{USER_SETTINGS_CALLBACK_PREFIX}prompt_lang_change") 
    builder.adjust(1)

    await message.answer(_("settings_menu_title"), reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML) # Tambahkan parse_mode

@user_settings_router.callback_query(F.data == f"{USER_SETTINGS_CALLBACK_PREFIX}main")
async def cq_back_to_settings_main(callback_query: types.CallbackQuery, _: callable, supabase_client: SupabaseClient, bot: Bot): # Tambahkan bot
    user_id = callback_query.from_user.id
    builder = InlineKeyboardBuilder()
    builder.button(text=_("button_change_language_settings"), callback_data=f"{USER_SETTINGS_CALLBACK_PREFIX}prompt_lang_change")
    builder.adjust(1)

    message_text = _("settings_menu_title")
    reply_markup = builder.as_markup()

    try:
        if callback_query.message.content_type == ContentType.PHOTO:
            await callback_query.message.edit_caption(caption=message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        elif callback_query.message.text:
            await callback_query.message.edit_text(text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else: # Fallback jika tidak bisa diedit
            await bot.send_message(user_id, message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            if callback_query.message.reply_markup: # Hapus keyboard dari pesan lama jika itu media tanpa caption
                 await callback_query.message.edit_reply_markup(reply_markup=None)

    except Exception as e:
        logging.info(f"Error editing message to settings main menu: {e}. Sending new message.")
        await bot.send_message(user_id, message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    await callback_query.answer()


@user_settings_router.callback_query(F.data == f"{USER_SETTINGS_CALLBACK_PREFIX}prompt_lang_change")
async def cq_prompt_language_change(callback_query: types.CallbackQuery, _: callable, supabase_client: SupabaseClient, bot: Bot): # Tambahkan bot
    user_id = callback_query.from_user.id

    current_lang_for_buttons = _.__self__.locale if hasattr(_,'__self__') and hasattr(_.__self__, 'locale') else DEFAULT_LANGUAGE

    keyboard_builder = await get_language_selection_keyboard(user_id, supabase_client, current_lang_for_buttons)

    message_text = _("select_your_language_prompt")
    reply_markup = keyboard_builder.as_markup()

    # PERUBAHAN DI SINI
    try:
        if callback_query.message.content_type == ContentType.PHOTO:
            await callback_query.message.edit_caption(caption=message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        elif callback_query.message.text: # Hanya edit jika ada teks
            await callback_query.message.edit_text(text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else: # Fallback jika tidak bisa diedit (misalnya, pesan media tanpa caption atau pesan layanan)
            logging.warning(f"Settings language prompt: Original message (ID: {callback_query.message.message_id}) is not a photo and has no text to edit. Sending new message.")
            await bot.send_message(user_id, text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            if callback_query.message.reply_markup: # Hapus keyboard dari pesan lama jika ada
                 await callback_query.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logging.error(f"Error editing message for language prompt: {e}. Sending new message.")
        await bot.send_message(user_id, text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

    await callback_query.answer()

@user_settings_router.callback_query(F.data.startswith(f"{USER_SETTINGS_CALLBACK_PREFIX}setlang_"))
async def cq_set_user_language_preference(callback_query: types.CallbackQuery, supabase_client: SupabaseClient, bot: Bot): # Tambahkan bot
    user_id = callback_query.from_user.id
    lang_code = callback_query.data.split("_")[1]

    if lang_code in AVAILABLE_LANGUAGES:
        success = await set_user_language(supabase_client, user_id, lang_code)

        new_translations = load_translations(lang_code)
        def get_new_lang_text(key, **kwargs):
            raw_text = new_translations.get(key, f"[{key}]")
            try:
                return raw_text.format(**kwargs)
            except KeyError:
                return raw_text

        if success:
            await callback_query.answer(get_new_lang_text("user_language_set_success", language_name=AVAILABLE_LANGUAGES[lang_code]), show_alert=True) 
        else:
            current_lang_for_error = DEFAULT_LANGUAGE
            # Logika untuk mendapatkan bahasa error bisa disederhanakan atau ditingkatkan
            error_translations = load_translations(current_lang_for_error) 
            def get_error_text_local(key):
                 return error_translations.get(key, f"[{key}]")
            await callback_query.answer(get_error_text_local("generic_error"), show_alert=True)

        # Perbarui keyboard pilihan bahasa
        # Setelah bahasa diubah, _ (get_text) dari middleware belum tentu langsung update untuk call ini.
        # Jadi, untuk teks tombol "Current", kita gunakan lang_code yang baru saja berhasil di-set.
        keyboard_builder = await get_language_selection_keyboard(user_id, supabase_client, lang_code if success else DEFAULT_LANGUAGE)

        # Pesan yang akan diedit adalah yang menampilkan pilihan bahasa
        # Teksnya adalah "select_your_language_prompt"
        # Kita perlu memuat ulang terjemahan untuk prompt ini dalam bahasa yang sesuai (bisa jadi bahasa baru atau bahasa lama jika gagal)
        lang_for_prompt_after_set = lang_code if success else (await get_user_language(supabase_client, user_id) or DEFAULT_LANGUAGE)
        translations_for_prompt = load_translations(lang_for_prompt_after_set)
        message_text_after_set = translations_for_prompt.get("select_your_language_prompt", "[select_your_language_prompt]")

        try:
            # Karena kita mengedit pesan yang sama (yang menampilkan pilihan bahasa),
            # dan pesan itu adalah teks (hasil dari edit sebelumnya di cq_prompt_language_change),
            # kita seharusnya bisa menggunakan edit_text atau edit_caption lagi.
            if callback_query.message.content_type == ContentType.PHOTO:
                 await callback_query.message.edit_caption(caption=message_text_after_set, reply_markup=keyboard_builder.as_markup(), parse_mode=ParseMode.HTML)
            elif callback_query.message.text:
                 await callback_query.message.edit_text(text=message_text_after_set, reply_markup=keyboard_builder.as_markup(), parse_mode=ParseMode.HTML)
            else: # Jarang terjadi, tapi sebagai fallback
                 await bot.send_message(user_id, text=message_text_after_set, reply_markup=keyboard_builder.as_markup(), parse_mode=ParseMode.HTML)

        except Exception as e:
            logging.warning(f"Failed to edit reply markup or text after setting user language: {e}")
    else:
        current_lang_for_error = DEFAULT_LANGUAGE
        error_translations = load_translations(current_lang_for_error)
        await callback_query.answer(error_translations.get("invalid_language_code", "Invalid language code."), show_alert=True)
