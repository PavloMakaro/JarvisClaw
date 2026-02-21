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
from core.ui.display import TelegramRenderer

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

    # Use new Renderer
    renderer = TelegramRenderer(context.bot, chat_id)
    await renderer.start("Analyzing request...")

    # Prepare context for tools
    tool_context = {
        "bot": context.bot,
        "chat_id": chat_id,
        "job_queue": context.job_queue
    }

    final_response = ""
    last_tool_msg = ""

    try:
        async for update_data in agent.run(user_input, chat_id, tool_context):
            status = update_data.get("status")

            if status == "thinking":
                msg = update_data.get("message", "Thinking...")
                await renderer.log_step(msg, "running")

            elif status == "plan_created":
                plan = update_data.get("plan")
                plan_text = "\n".join([f"- {t['tool']}" for t in plan])
                await renderer.append_log(f"📋 **Plan Created:**\n{plan_text}")

            elif status == "tool_use":
                tool = update_data.get("tool")
                last_tool_msg = f"Executing {tool}..."
                await renderer.log_step(last_tool_msg, "running")

            elif status == "observation":
                result = update_data.get("result")
                short_result = (str(result)[:100] + "...") if len(str(result)) > 100 else str(result)
                # Mark previous running step as done
                await renderer.update_last_log(f"✅ {last_tool_msg} (Result: {short_result})")

            elif status == "executing":
                msg = update_data.get("message", "Executing...")
                await renderer.log_step(msg, "running")

            elif status == "final_stream":
                content = update_data.get("content")
                final_response += content
                # We don't stream to log, we wait for finish

            elif status == "final":
                if update_data.get("content"):
                    final_response = update_data.get("content")

            elif status == "error":
                error_msg = update_data.get("message")
                await renderer.append_log(f"❌ Error: {error_msg}")

        # Send final response
        if final_response:
            await renderer.finish(final_response)
        else:
            await renderer.finish("I'm done, but I have no response.")

    except Exception as e:
        logger.error(f"Error handling message: {e}")
        try:
            await renderer.finish(f"Error: {str(e)}")
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
