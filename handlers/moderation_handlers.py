import logging
from aiogram import Router, types, F, Bot
from aiogram.exceptions import TelegramForbiddenError
from supabase import Client as SupabaseClient
from utils.supabase_interface import get_ai_config, get_group_language
from utils.crypto_interface import CryptoUtil
from utils.groq_interface import get_groq_completion
from utils.helpers import escape_html_tags
from bot_config import (
    DEFAULT_GROQ_MODEL, MODERATION_LEVELS, DEFAULT_MODERATION_LEVEL,
    DEFAULT_LANGUAGE
)
from middlewares.i18n_middleware import load_translations
from handlers.ai_response_handlers import process_ai_request

moderation_router = Router()

async def perform_text_moderation(
    bot: Bot,
    message_text: str,
    group_id: int,
    group_name: str,
    user_id: int,
    user_full_name: str,
    config: dict,
    supabase_client: SupabaseClient,
    crypto_util: CryptoUtil,
    _: callable,
    original_message_id: int
):
    current_moderation_level = config.get('moderation_level', DEFAULT_MODERATION_LEVEL)
    decrypted_api_key = None

    if config.get("encrypted_groq_api_key"):
        decrypted_api_key = crypto_util.decrypt_data(config.get("encrypted_groq_api_key"))

    if not decrypted_api_key:
        logging.warning(f"PERFORM_MOD: API Key not available or decryption failed for group {group_id}. Skipping.")
        return False

    if current_moderation_level == DEFAULT_MODERATION_LEVEL:
        logging.info(f"PERFORM_MOD: Moderation for group {group_id} is effectively disabled (level: {current_moderation_level}). Skipping text: '{message_text[:50]}...'")
        return False

    moderation_prompt_level_text = current_moderation_level
    moderation_prompt = f"You are a content moderation AI. Analyze the following text, in any language, for any forbidden content. This includes, but is not limited to: profanity (e.g., 'kata kotor' in Indonesian; Javanese swear words like 'asu', 'dck', and similar terms; swear words in any other language), hate speech, explicit adult content, severe violence, self-harm encouragement, harassment, or illegal activities. Respond with ONLY 'FLAGGED: [REASON]' if it violates policies, or 'SAFE' if it does not. Be more sensitive if the requested level is higher. Current Level: {moderation_prompt_level_text}. Text to analyze: \"{message_text}\""
    moderation_model = config.get("groq_model", DEFAULT_GROQ_MODEL)

    logging.info(f"PERFORM_MOD: Attempting moderation for group {group_id} with level '{current_moderation_level}' for text: '{message_text[:50]}...'")
    action_taken = False
    try:
        response_data = await get_groq_completion(
            api_key=decrypted_api_key,
            model=moderation_model,
            system_prompt_for_call="You are an AI content moderator.",
            user_prompt_for_call=moderation_prompt,
            full_messages_list=[
                {"role": "system", "content": "You are an AI content moderator. Your task is to analyze text based on the user's instructions and determine if it should be flagged."},
                {"role": "user", "content": moderation_prompt}
            ]
        )
        logging.info(f"PERFORM_MOD: Raw Groq moderation response_data for group {group_id}: {response_data}")

        if response_data and response_data.get("main_response"):
            ai_decision_raw = response_data.get("main_response").strip()
            logging.info(f"PERFORM_MOD: Moderation AI decision for group {group_id}, level {current_moderation_level}: '{ai_decision_raw}' for text: '{message_text[:100]}...'")

            if ai_decision_raw.startswith("FLAGGED:"):
                action_taken = True
                reason_raw = ai_decision_raw.split("FLAGGED:", 1)[1].strip()
                reason_text = reason_raw if reason_raw else _("moderation_reason_suspicious_text")
                reason = escape_html_tags(reason_text)

                warning_message_key = "moderation_warning_text"
                warning_text_params = { "group_name": escape_html_tags(group_name), "reason": reason }
                group_lang = await get_group_language(supabase_client, group_id)
                specific_translations = load_translations(group_lang)
                user_warning_text = specific_translations.get(warning_message_key, "Warning: Your message was flagged.").format(**warning_text_params)
                try:
                    await bot.send_message(chat_id=group_id, text=user_warning_text, reply_to_message_id=original_message_id)
                    logging.info(f"PERFORM_MOD: Moderation warning sent to user {user_id} in group {group_id} for reason: {reason}")
                except Exception as e_send_user_warn:
                    logging.error(f"PERFORM_MOD: Failed to send moderation warning to user in group {group_id}: {e_send_user_warn}")

                try:
                    chat_admins = await bot.get_chat_administrators(chat_id=group_id)
                    admin_notification_text_key = "moderation_admin_notification_text"
                    safe_group_name = escape_html_tags(group_name)
                    safe_user_full_name = escape_html_tags(user_full_name)
                    admin_notification_params = {
                        "group_name": safe_group_name, "user_full_name": safe_user_full_name,
                        "user_id": user_id, "reason": reason,
                        "message_text": escape_html_tags(message_text[:200])
                    }
                    for admin in chat_admins:
                        if not admin.user.is_bot:
                            try:
                                admin_translations = load_translations(DEFAULT_LANGUAGE)
                                admin_message_text = admin_translations.get(admin_notification_text_key, "Moderation Alert").format(**admin_notification_params)
                                await bot.send_message(chat_id=admin.user.id, text=admin_message_text)
                                await bot.forward_message(chat_id=admin.user.id, from_chat_id=group_id, message_id=original_message_id)
                                logging.info(f"PERFORM_MOD: Violation forwarded to admin {admin.user.id} for group {group_id}")
                            except TelegramForbiddenError:
                                logging.warning(f"PERFORM_MOD: Could not forward violation to admin {admin.user.id}. Bot might be blocked or chat not initiated.")
                            except Exception as e_fwd:
                                logging.error(f"PERFORM_MOD: Failed to forward violation to admin {admin.user.id}: {e_fwd}")
                except Exception as e_get_admins:
                    logging.error(f"PERFORM_MOD: Could not get chat administrators for group {group_id}: {e_get_admins}")
            elif ai_decision_raw.upper() == 'SAFE':
                logging.info(f"PERFORM_MOD: Moderation AI for group {group_id} deemed text SAFE: '{message_text[:100]}...'")
            else:
                logging.warning(f"PERFORM_MOD: Moderation AI for group {group_id} returned an unexpected decision: '{ai_decision_raw}' for text: '{message_text[:100]}...'")
        else:
            logging.warning(f"PERFORM_MOD: Moderation AI for group {group_id} returned no response_data or empty main_response.")
    except Exception as e:
        logging.error(f"PERFORM_MOD: Error during text moderation for group {group_id}: {e}")
    return action_taken


# PERUBAHAN FILTER DI SINI:
@moderation_router.message(F.text & F.chat.type.in_({'group', 'supergroup'}) & ~F.text.startswith('/'))
async def handle_group_text_message(
    message: types.Message,
    supabase_client: SupabaseClient,
    crypto_util: CryptoUtil,
    _: callable,
    bot: Bot
):
    group_id = message.chat.id
    user = message.from_user
    config = await get_ai_config(supabase_client, group_id)

    logging.info(f"MOD_ INTEGRATED_HANDLER: Received non-command text in group {group_id} from user {user.id} ('{message.text[:50]}...').")

    if not config:
        logging.info(f"MOD_ INTEGRATED_HANDLER: No config found for group {group_id}. Skipping all processing for this message.")
        return

    # --- 1. Moderation Part ---
    moderation_performed_action = False # Untuk melacak apakah moderasi melakukan sesuatu
    if config.get('moderation_level', DEFAULT_MODERATION_LEVEL) != DEFAULT_MODERATION_LEVEL:
        if not (user.is_bot and user.id == bot.id):
            logging.info(f"MOD_ INTEGRATED_HANDLER: Moderation is active for group {group_id}. Calling perform_text_moderation.")
            moderation_performed_action = await perform_text_moderation(
                bot=bot, message_text=message.text, group_id=group_id,
                group_name=message.chat.title or "this group", user_id=user.id,
                user_full_name=user.full_name, config=config,
                supabase_client=supabase_client, crypto_util=crypto_util, _=_,
                original_message_id=message.message_id
            )
        else:
            logging.info(f"MOD_ INTEGRATED_HANDLER: Message from our bot in group {group_id}. Skipping moderation part.")
    else:
        logging.info(f"MOD_ INTEGRATED_HANDLER: Moderation is disabled for group {group_id}. Skipping moderation part.")

    # --- 2. AI Response Part (Mention & Custom Prefix) ---
    user_question_for_ai = None
    ai_trigger_type = None

    if config.get('is_active', False):
        bot_info = await bot.get_me()
        bot_username_lower = bot_info.username.lower()

        if config.get('ai_trigger_mention_enabled', True):
            temp_question = None
            if message.text.lower().startswith(f"@{bot_username_lower}"):
                parts = message.text.split(maxsplit=1)
                if len(parts) > 1: temp_question = parts[1].strip()
            elif message.entities:
                for entity in message.entities:
                    if entity.type == "mention":
                        mention_text_in_message = message.text[entity.offset : entity.offset + entity.length]
                        if mention_text_in_message.lower() == f"@{bot_username_lower}":
                            temp_question = message.text[entity.offset + entity.length :].strip()
                            break
            if temp_question:
                user_question_for_ai = temp_question
                ai_trigger_type = "mention"

        if not user_question_for_ai and config.get('ai_trigger_custom_prefix'):
            custom_prefix = config.get('ai_trigger_custom_prefix')
            if message.text.startswith(custom_prefix):
                question_candidate = message.text[len(custom_prefix):].strip()
                if question_candidate:
                    user_question_for_ai = question_candidate
                    ai_trigger_type = "custom_prefix"

        if user_question_for_ai:
            logging.info(f"MOD_ INTEGRATED_HANDLER: AI Q&A triggered by {ai_trigger_type} for group {group_id}. Question: '{user_question_for_ai[:50]}...'")
            await process_ai_request(message, user_question_for_ai, supabase_client, crypto_util, _)
        else:
            if not moderation_performed_action:
                 logging.info(f"MOD_ INTEGRATED_HANDLER: Message in group {group_id} was not a command, and not an AI mention/prefix. Moderation also took no action or was off.")
    else:
        logging.info(f"MOD_ INTEGRATED_HANDLER: AI Q&A is inactive for group {group_id}.")
