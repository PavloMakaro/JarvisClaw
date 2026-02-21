import asyncio
import logging
import time
from typing import List, Optional

class TelegramRenderer:
    """
    Handles the display of agent execution in a CLI-like style on Telegram.
    Updates a single message (or multiple if needed) to show the "thought process".
    """
    def __init__(self, bot, chat_id: str):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id: Optional[int] = None
        self.logs: List[str] = []
        self.last_update_time = 0
        self.update_interval = 1.0 # Seconds between updates to avoid rate limits
        self.logger = logging.getLogger("TelegramRenderer")
        self.is_finished = False

    async def start(self, initial_text="Thinking..."):
        """Sends the initial message."""
        try:
            msg = await self.bot.send_message(
                chat_id=self.chat_id,
                text=f"Wait, I'm thinking...\n\n{initial_text}",
                parse_mode="Markdown"
            )
            self.message_id = msg.message_id
            self.logs.append(initial_text)
        except Exception as e:
            # Fallback for markdown errors
            msg = await self.bot.send_message(
                chat_id=self.chat_id,
                text=f"Wait, I'm thinking...\n\n{initial_text}"
            )
            self.message_id = msg.message_id
            self.logs.append(initial_text)

    async def log_step(self, step_name: str, status: str = "running"):
        """Adds a step to the log."""
        icon = "⏳" if status == "running" else "✅" if status == "completed" else "❌"
        text = f"{icon} **{step_name}**"
        self.logs.append(text)
        await self._schedule_update()

    async def update_last_log(self, new_text: str):
        """Updates the last log entry (e.g., to show result or completion)."""
        if self.logs:
            self.logs[-1] = new_text
            await self._schedule_update()

    async def append_log(self, text: str):
        """Appends a raw log line."""
        self.logs.append(text)
        await self._schedule_update()

    async def _schedule_update(self):
        """Updates the message if enough time has passed, or schedules it."""
        current_time = time.time()
        if current_time - self.last_update_time >= self.update_interval:
            await self._update_display()
        # Note: In a real async app, we might want a background task to flush updates
        # but here we'll just rely on the next call or the final update.

    async def _update_display(self):
        """Performs the actual API call to edit the message."""
        if not self.message_id:
            return

        self.last_update_time = time.time()

        # Format logs
        # Keep only last N logs if too long?
        # For CLI feel, we want to show the history.
        # Telegram limit is 4096 chars.

        full_text = "\n".join(self.logs)

        # Truncate head if too long
        if len(full_text) > 3800:
            full_text = "...(previous steps)...\n" + full_text[-(3800):]

        header = "🧠 **Process Log:**\n"
        final_text = header + full_text

        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=final_text,
                parse_mode="Markdown"
            )
        except Exception as e:
            # Ignore "message is not modified"
            if "not modified" in str(e):
                pass
            else:
                self.logger.warning(f"Failed to update display: {e}")
                # Try plain text fallback
                try:
                    await self.bot.edit_message_text(
                        chat_id=self.chat_id,
                        message_id=self.message_id,
                        text=final_text.replace("*", "").replace("_", ""), # Strip markdown
                        parse_mode=None
                    )
                except Exception as e2:
                    self.logger.error(f"Failed plain text fallback: {e2}")

    async def finish(self, final_response: str):
        """
        Finalizes the process.
        If the response is short, append to log.
        If long, send as new message.
        """
        self.is_finished = True

        # Update log one last time with "Done"
        await self.append_log("\n✅ **Finished**")
        await self._update_display()

        # Send the actual response as a new message
        try:
            # Split if too long
            max_len = 4000
            if len(final_response) > max_len:
                for i in range(0, len(final_response), max_len):
                    chunk = final_response[i:i+max_len]
                    await self.bot.send_message(
                        chat_id=self.chat_id,
                        text=chunk,
                        parse_mode="Markdown"
                    )
            else:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=final_response,
                    parse_mode="Markdown"
                )
        except Exception:
            # Fallback
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=final_response
            )
