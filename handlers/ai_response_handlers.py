import uuid
import logging
from aiogram import Router, types, F
from aiogram.filters import Command
# from aiogram.enums import ParseMode 
from aiogram.utils.keyboard import InlineKeyboardBuilder
from supabase import Client as SupabaseClient

from utils.supabase_interface import get_ai_config, add_conversation_message, get_conversation_history
from utils.crypto_interface import CryptoUtil
from utils.groq_interface import get_groq_completion
from utils.helpers import escape_html_tags 
from bot_config import DEFAULT_GROQ_MODEL 

ai_response_router = Router()

pending_thoughts_cache: dict[str, str] = {}
THOUGHTS_CALLBACK_PREFIX = "show_thoughts:"


async def process_ai_request(message: types.Message, user_question: str, supabase_client: SupabaseClient, crypto_util: CryptoUtil, _: callable):
    group_id = message.chat.id
    config = await get_ai_config(supabase_client, group_id)

    if not config:
        await message.reply(_("ai_error_no_api_key"))
        return

    if not config.get("is_active", False):
        await message.reply(_("ai_error_config_inactive"))
        return

    encrypted_api_key = config.get("encrypted_groq_api_key")
    if not encrypted_api_key:
        await message.reply(_("ai_error_no_api_key"))
        return

    decrypted_api_key = crypto_util.decrypt_data(encrypted_api_key)
    if not decrypted_api_key:
        await message.reply(_("ai_error_decryption_failed"))
        return

    system_prompt_text = config.get("system_prompt", "You are a helpful assistant.")
    groq_model = config.get("groq_model", DEFAULT_GROQ_MODEL)

    thinking_message = await message.reply(_("ai_thinking"))

    history_messages_db = await get_conversation_history(supabase_client, group_id)
    messages_for_groq = [{"role": "system", "content": system_prompt_text}]
    for hist_msg in history_messages_db:
        messages_for_groq.append({"role": hist_msg["role"], "content": hist_msg["content"]})
    messages_for_groq.append({"role": "user", "content": user_question})

    parsed_groq_response = await get_groq_completion(
        api_key=decrypted_api_key,
        model=groq_model,
        system_prompt_for_call="", 
        user_prompt_for_call="",   
        full_messages_list=messages_for_groq
    )

    if parsed_groq_response:
        main_response_raw = parsed_groq_response.get("main_response")
        thoughts_content = parsed_groq_response.get("thoughts")

        if main_response_raw:
            # Simpan ke history sebelum di-escape untuk tampilan
            await add_conversation_message(supabase_client, group_id, "user", user_question)
            await add_conversation_message(supabase_client, group_id, "assistant", main_response_raw)

            if main_response_raw.startswith("GROQ_API_ERROR:") or main_response_raw.startswith("UNEXPECTED_GROQ_ERROR:"):
                error_details_raw = main_response_raw.split(":", 1)[1].strip() if ":" in main_response_raw else main_response_raw
                safe_error_details = escape_html_tags(error_details_raw)
                await thinking_message.edit_text(_("ai_error_groq_api", error_details=safe_error_details))
            else:
                safe_ai_response = escape_html_tags(main_response_raw)
                response_to_send = safe_ai_response

                if (main_response_raw.strip().startswith("```") and main_response_raw.strip().endswith("```")):
                    code_content = main_response_raw.strip()[3:-3]
                    if '\n' in code_content:
                        first_line, rest_of_code = code_content.split('\n', 1)
                        common_langs = ["html", "python", "javascript", "css", "json", "sql", "java", "c", "c++", "csharp", "latex", ""]
                        if first_line.strip().lower() in common_langs:
                            code_content = rest_of_code
                        # else: code_content tetap sama (mengandung penanda bahasa atau tidak)
                    response_to_send = f"<pre><code>{escape_html_tags(code_content.strip())}</code></pre>"
                elif (main_response_raw.count('\n') > 3 and len(main_response_raw) > 100) or \
                     main_response_raw.strip().lower().startswith("<!doctype html") or \
                     main_response_raw.strip().lower().startswith("<html") or \
                     main_response_raw.strip().lower().startswith("<?xml"):
                    response_to_send = f"<pre>{safe_ai_response}</pre>"

                reply_markup = None
                if thoughts_content:
                    thought_id = str(uuid.uuid4())
                    pending_thoughts_cache[thought_id] = thoughts_content
                    builder = InlineKeyboardBuilder()
                    builder.button(text=_("button_show_thoughts"), callback_data=f"{THOUGHTS_CALLBACK_PREFIX}{thought_id}")
                    reply_markup = builder.as_markup()

                try:
                    if len(response_to_send) > 4000: 
                        first_chunk = True
                        for i in range(0, len(response_to_send), 4000):
                            chunk = response_to_send[i:i+4000]
                            if first_chunk:
                                await thinking_message.edit_text(chunk, reply_markup=reply_markup if i == 0 else None)
                                first_chunk = False
                            else:
                                await message.reply(chunk)
                    else:
                        await thinking_message.edit_text(response_to_send, reply_markup=reply_markup)
                except Exception as e_send:
                    logging.error(f"Error sending AI response even after HTML escaping: {repr(e_send)}. Original AI raw: {main_response_raw}")
                    await thinking_message.edit_text(_("ai_error_generic") + "(Could not display formatted response)")
        else: 
             await thinking_message.edit_text(_("generic_error") + " (Empty AI response)")
    else:
        await thinking_message.edit_text(_("generic_error"))
# --- AKHIR DEFINISI process_ai_request ---


@ai_response_router.message(Command("ask_ai"), F.text)
async def cmd_ask_ai(message: types.Message, command: Command, supabase_client: SupabaseClient, crypto_util: CryptoUtil, _: callable):
    group_id = message.chat.id
    config = await get_ai_config(supabase_client, group_id)

    # Cek apakah pemicu perintah diaktifkan
    if not (config and config.get('ai_trigger_command_enabled', True)): # Default True jika tidak ada di DB
        # Abaikan jika tidak aktif, atau kirim pesan bahwa perintah dinonaktifkan
        # print(f"Debug: /ask_ai trigger disabled for group {group_id}")
        return 

    if command.args is None:
        await message.reply(_("ask_ai_no_question_prompt"))
        return
    user_question = command.args.strip()
    if not user_question:
        await message.reply(_("ask_ai_no_question_prompt"))
        return
    await process_ai_request(message, user_question, supabase_client, crypto_util, _)


# HANDLER BARU UNTUK CUSTOM PREFIX
# Filter ini akan berjalan untuk semua pesan teks yang bukan perintah dan bukan mention eksplisit
# Kita perlu pastikan ini tidak terlalu greedy.
# Filter F.text saja, lalu cek prefix di dalam handler.



@ai_response_router.callback_query(F.data.startswith(THOUGHTS_CALLBACK_PREFIX))
async def cq_show_thoughts(callback_query: types.CallbackQuery, _: callable):
    thought_id = callback_query.data.split(THOUGHTS_CALLBACK_PREFIX)[1]
    thoughts_text_raw = pending_thoughts_cache.pop(thought_id, None)

    if thoughts_text_raw:
        safe_thoughts_text = escape_html_tags(thoughts_text_raw) 
        header = _("ai_thoughts_header") 
        full_thought_message = f"{header}\n<pre>{safe_thoughts_text}</pre>"

        if len(full_thought_message) > 4096 :
            for i in range(0, len(full_thought_message), 4090): 
                chunk_to_send = full_thought_message[i:i+4090]
                if callback_query.message:
                    await callback_query.message.reply(chunk_to_send) 
                else:
                    await callback_query.bot.send_message(callback_query.from_user.id, chunk_to_send)
            await callback_query.answer()
        else:
            try:
                if callback_query.message:
                     await callback_query.message.reply(full_thought_message) 
                else:
                     await callback_query.bot.send_message(callback_query.from_user.id, full_thought_message)
                await callback_query.answer() 
            except Exception as e:
                print(f"Error sending thoughts: {e}")
                await callback_query.answer(_("generic_error"), show_alert=True)
    else:
        await callback_query.answer("Sorry, I couldn't retrieve the thought process. It might have expired.", show_alert=True)
