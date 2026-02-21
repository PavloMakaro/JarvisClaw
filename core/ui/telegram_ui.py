import time
import asyncio
import logging
from core.display import DisplayManager

class TelegramUIManager:
    def __init__(self, bot):
        self.bot = bot
        self.last_edit_time = 0
        self.last_rendered_text = ""
        self.logger = logging.getLogger("TelegramUI")
        self.display_manager = DisplayManager()

    async def send_initial_status(self, chat_id, text="Thinking..."):
        """Sends the initial status message and returns it."""
        try:
            msg = await self.bot.send_message(chat_id=chat_id, text=text)
            self.last_rendered_text = text
            return msg
        except Exception as e:
            self.logger.error(f"Failed to send initial status: {e}")
            return None

    async def update_status(self, chat_id, message_id, update_data, force=False):
        """
        Updates the status message with rate limiting.
        update_data can be a string (legacy) or a dict (structured update).
        """
        current_time = time.time()

        # Update the display manager state if structured data is provided
        if isinstance(update_data, dict):
            self.display_manager.update(update_data)
            display_text = self.display_manager.render()
        else:
            # Legacy string update - set thought directly
            self.display_manager.update({"thought": str(update_data)})
            display_text = str(update_data)

        # Rate limit: max 1 edit per second unless forced
        if not force and (current_time - self.last_edit_time < 1.5):
            return

        if display_text == self.last_rendered_text:
            return

        try:
            # Simple truncation to avoid Telegram limits
            if len(display_text) > 4000:
                display_text = display_text[:3997] + "..."

            await self.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=display_text,
                parse_mode="Markdown" # Use Markdown for formatting
            )
            self.last_rendered_text = display_text
            self.last_edit_time = current_time
        except Exception as e:
            # Ignore "Message is not modified" errors
            if "not modified" not in str(e):
                self.logger.warning(f"Failed to update status: {e}")
                # Fallback to plain text if Markdown fails
                try:
                    await self.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=display_text,
                        parse_mode=None
                    )
                except Exception as e2:
                    self.logger.error(f"Failed to update status fallback: {e2}")

    async def send_final_response(self, chat_id, message_id, text, preserve_status=True):
        """
        Sends the final response.
        If preserve_status is True, sends as a NEW message and leaves the status message alone (or updates it one last time).
        If preserve_status is False, overwrites the status message.
        """
        try:
            # Split if too long
            max_len = 4000
            chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]

            if preserve_status:
                # Send all chunks as new messages
                for chunk in chunks:
                    try:
                        await self.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="Markdown")
                    except:
                        await self.bot.send_message(chat_id=chat_id, text=chunk)
            else:
                # Edit first chunk into status message
                first_chunk = chunks[0]
                try:
                    await self.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=first_chunk,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    # Fallback to plain text if Markdown fails
                    await self.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=first_chunk
                    )

                # Send remaining chunks as new messages
                for chunk in chunks[1:]:
                    try:
                        await self.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="Markdown")
                    except:
                        await self.bot.send_message(chat_id=chat_id, text=chunk)

        except Exception as e:
            self.logger.error(f"Failed to send final response: {e}")
            # Try sending as new message if edit fails completely
            try:
                await self.bot.send_message(chat_id=chat_id, text=text)
            except:
                pass
