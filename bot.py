import logging
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)
import config
from core.agent import Agent
from core.ui.telegram_ui import TelegramUIManager

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Agent
agent = Agent()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Hello! I am your AI assistant (V2). I am ready to help.",
    )

async def clear_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    await agent.episodic_memory.clear(chat_id)
    await context.bot.send_message(chat_id=chat_id, text="Memory cleared.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    chat_id = str(update.effective_chat.id)

    ui = TelegramUIManager(context.bot)

    # Send initial status
    status_msg = await ui.send_initial_status(chat_id, "Thinking...")
    if not status_msg:
        logger.error("Could not send status message.")
        return

    # Prepare context for tools
    tool_context = {
        "bot": context.bot,
        "chat_id": chat_id,
        "job_queue": context.job_queue
    }

    final_response = ""

    try:
        async for update_data in agent.run(user_input, chat_id, tool_context):
            status = update_data.get("status")

            if status == "thinking":
                msg = f"Thinking: {update_data.get('message', '...')}"
                await ui.update_status(chat_id, status_msg.message_id, msg)

            elif status == "tool_use":
                tool = update_data.get("tool")
                msg = f"Executing: {tool}..."
                await ui.update_status(chat_id, status_msg.message_id, msg)

            elif status == "plan_created":
                plan = update_data.get("plan")
                steps = len(plan)
                msg = f"Plan created ({steps} steps). Executing..."
                await ui.update_status(chat_id, status_msg.message_id, msg)

            elif status == "executing":
                msg = f"Executing plan..."
                await ui.update_status(chat_id, status_msg.message_id, msg)

            elif status == "final_stream":
                content = update_data.get("content")
                final_response += content
                # Update UI periodically with accumulated content + cursor
                await ui.update_status(chat_id, status_msg.message_id, final_response + " ▌")

            elif status == "final":
                # Final content might be in 'content' if not streamed, or we use accumulated
                if update_data.get("content"):
                    final_response = update_data.get("content")

        # Send final response (overwrite status message with final text)
        if final_response:
            await ui.send_final_response(chat_id, status_msg.message_id, final_response)
        else:
            await ui.send_final_response(chat_id, status_msg.message_id, "Error: No response generated.")

    except Exception as e:
        logger.error(f"Error handling message: {e}")
        # Try to update message with error
        try:
            await ui.send_final_response(chat_id, status_msg.message_id, f"Error: {str(e)}")
        except:
            await context.bot.send_message(chat_id=chat_id, text=f"Error: {str(e)}")

if __name__ == "__main__":
    if not hasattr(config, "TELEGRAM_BOT_TOKEN") or not config.TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found in config.py")
        sys.exit(1)

    application = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("clear", clear_memory))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("Bot V2 is running...")
    application.run_polling()
