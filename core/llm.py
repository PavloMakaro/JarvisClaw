import os
from openai import AsyncOpenAI
from typing import AsyncGenerator, Union, List, Dict, Any
import config

class LLMService:
    def __init__(self):
        # Initialize Groq client
        self.groq_client = AsyncOpenAI(
            api_key=config.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )

        # Initialize DeepSeek client
        self.deepseek_client = AsyncOpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )

    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: str = "llama3-70b-8192", # Groq model default
        provider: str = "groq",
        temperature: float = 0.7,
        stream: bool = False,
        tools: List[Dict[str, Any]] = None,
        tool_choice: str = "auto",
    ) -> Union[Any, AsyncGenerator[Any, None]]:
        """
        Generates response via Groq or DeepSeek API.
        Returns message object (non-stream) or async generator of chunks (stream).
        """
        try:
            client = self.groq_client
            if provider == "deepseek":
                client = self.deepseek_client
                if model == "default":
                    model = "deepseek-chat"

            # Prepare args
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "stream": stream
            }

            # Only add tools if provided and not empty
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice

            # DeepSeek fix: if tools is None or empty, do NOT pass tool_choice at all
            if not tools and "tools" in kwargs:
                del kwargs["tools"]
            if not tools and "tool_choice" in kwargs:
                del kwargs["tool_choice"]

            if stream:
                response = await client.chat.completions.create(**kwargs)

                # Wrap generator to yield raw chunks
                async def stream_generator() -> AsyncGenerator[Any, None]:
                    async for chunk in response:
                        yield chunk

                return stream_generator()

            else:
                response = await client.chat.completions.create(**kwargs)
                return response.choices[0].message

        except Exception as e:
            error_msg = f"Error generating response: {str(e)}"

            # Return a mock message object with error content instead of raw string
            class ErrorMessage:
                content = error_msg
                tool_calls = None

            if stream:
                async def error_gen() -> AsyncGenerator[Any, None]:
                    class ErrorChunk:
                        class Choice:
                            class Delta:
                                content = error_msg
                                tool_calls = None
                            delta = Delta()
                        choices = [Choice()]
                    yield ErrorChunk()
                return error_gen()

            return ErrorMessage()
