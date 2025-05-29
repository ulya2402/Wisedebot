import logging
import re
from aiogram import Bot, Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from utils.helpers import escape_html_tags


message_sending_router = Router()

async def is_user_chat_admin(bot_instance: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot_instance.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except TelegramAPIError:
        return False


@message_sending_router.message(Command("sendmsg"), F.chat.type == "private")
async def cmd_send_message_to_group(message: types.Message, command: Command, bot: Bot, _: callable):
    if command.args is None:
        await message.reply(_("sendmsg_prompt_format_dm"))
        return

    match = re.match(r"^(-?\d+)(?:\s+(\d+))?\s+(.+)$", command.args, re.DOTALL)

    if not match:
        await message.reply(_("sendmsg_prompt_format_dm"))
        return

    target_group_id_str = match.group(1)
    topic_id_str = match.group(2)
    message_text_to_send = match.group(3)

    try:
        target_group_id = int(target_group_id_str)
    except ValueError:
        await message.reply(_("sendmsg_invalid_group_id_format_dm", group_id=escape_html_tags(target_group_id_str)))
        return

    message_thread_id = None
    if topic_id_str:
        try:
            message_thread_id = int(topic_id_str)
        except ValueError:
            await message.reply(_("sendmsg_invalid_topic_id_format_dm", topic_id=escape_html_tags(topic_id_str)))
            return

    sender_user_id = message.from_user.id
    # Gunakan fungsi is_user_chat_admin yang sudah didefinisikan di atas atau impor
    is_sender_admin_of_target = await is_user_chat_admin(bot, target_group_id, sender_user_id)

    if not is_sender_admin_of_target:
        target_group_name = str(target_group_id)
        try:
            chat_info = await bot.get_chat(target_group_id)
            if chat_info.title:
                target_group_name = chat_info.title
        except Exception:
            pass
        await message.reply(_("sendmsg_not_admin_of_group_dm", group_name=escape_html_tags(target_group_name)))
        return

    try:
        await bot.send_message(
            chat_id=target_group_id,
            text=message_text_to_send,
            message_thread_id=message_thread_id,
            parse_mode=ParseMode.HTML
        )
        target_group_name_for_feedback = str(target_group_id)
        try:
            chat_info_feedback = await bot.get_chat(target_group_id)
            if chat_info_feedback.title:
                target_group_name_for_feedback = chat_info_feedback.title
        except Exception:
            pass

        if message_thread_id:
            await message.reply(_("sendmsg_message_sent_success_topic_dm", topic_id=message_thread_id, group_name=escape_html_tags(target_group_name_for_feedback)))
        else:
            await message.reply(_("sendmsg_message_sent_success_dm", group_name=escape_html_tags(target_group_name_for_feedback)))
        logging.info(f"Admin {sender_user_id} sent message to group {target_group_id} (topic: {message_thread_id}): {message_text_to_send[:50]}...")

    except TelegramForbiddenError as e:
        logging.error(f"Failed to send message via /sendmsg to group {target_group_id}: Forbidden - {e}")
        await message.reply(_("sendmsg_forbidden_or_not_member_dm"))
    except TelegramAPIError as e:
        logging.error(f"Failed to send message via /sendmsg to group {target_group_id}: API Error - {e}")
        if message_thread_id and ("message thread not found" in str(e).lower() or "thread_id is_invalid" in str(e).lower() or "topic_id_invalid" in str(e).lower()):
            await message.reply(_("sendmsg_invalid_topic_id_dm", topic_id=message_thread_id))
        else:
            await message.reply(_("sendmsg_generic_send_failed_dm", error_details=escape_html_tags(str(e))))
    except Exception as e:
        logging.error(f"Unexpected error in /sendmsg to group {target_group_id}: {e}")
        await message.reply(_("generic_error"))
