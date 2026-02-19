import asyncio
import logging
from typing import Dict, Any, AsyncGenerator

from core.llm import LLMService
from core.module_manager import ModuleManager
from core.memory.vector_memory import VectorMemory
from core.memory.episodic_memory import EpisodicMemory
from core.decision import DecisionLayer
from core.planner import Planner
from core.executor import Executor

import os

class Agent:
    def __init__(self):
        self.llm = LLMService()
        self.module_manager = ModuleManager()
        self.module_manager.load_modules()

        self.vector_memory = VectorMemory()
        self.episodic_memory = EpisodicMemory()

        self.decision_layer = DecisionLayer(self.llm)
        self.planner = Planner(self.llm)
        self.executor = Executor(self.module_manager)

        self.logger = logging.getLogger("Agent")

        # Load system prompt
        self.system_prompt = "You are a helpful AI assistant."
        try:
            if os.path.exists("system_prompt.txt"):
                with open("system_prompt.txt", "r", encoding="utf-8") as f:
                    self.system_prompt = f.read()
            elif os.path.exists("system_prompt_structured.txt"):
                with open("system_prompt_structured.txt", "r", encoding="utf-8") as f:
                    self.system_prompt = f.read()
        except Exception as e:
            self.logger.error(f"Error loading system prompt: {e}")

    async def run(self, user_input: str, chat_id: str, context: Dict[str, Any] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Main execution loop.
        Yields status updates and final response.
        """
        if context is None:
            context = {}

        # 1. Load History
        history = await self.episodic_memory.get_history(chat_id)

        # 2. Get Tool Definitions
        tools = self.module_manager.get_definitions()

        yield {"status": "thinking", "message": "Analyzing request..."}

        # 3. Decision Layer
        try:
            decision = await self.decision_layer.decide(user_input, history, tools)
            self.logger.info(f"Decision for {chat_id}: {decision}")
        except Exception as e:
            self.logger.error(f"Decision failed: {e}")
            decision = {"decision": "RESPOND_DIRECTLY"}

        action = decision.get("decision")

        final_response = ""

        if action == "RESPOND_DIRECTLY":
            yield {"status": "thinking", "message": "Drafting response..."}
            # Generate response using LLM
            messages = list(history)
            messages.append({"role": "user", "content": user_input})

            # Simple prompt wrapper?
            # Or just pass messages directly
            # We might want to inject system prompt here if not present
            if not messages or messages[0]["role"] != "system":
                 messages.insert(0, {"role": "system", "content": self.system_prompt})

            stream = await self.llm.generate(messages, stream=True, provider="deepseek")

            async for chunk in stream:
                if hasattr(chunk, 'choices') and chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield {"status": "final_stream", "content": delta.content}
                        final_response += delta.content

        elif action == "USE_TOOL":
            tool_name = decision.get("tool_name")
            tool_args = decision.get("tool_args", {})
            yield {"status": "tool_use", "tool": tool_name, "args": tool_args}

            try:
                # Execute tool
                result = await self._execute_tool_safe(tool_name, tool_args, context)

                yield {"status": "observation", "result": str(result)}

                # Generate final response with tool output
                yield {"status": "thinking", "message": "Synthesizing answer..."}

                messages = list(history)
                messages.append({"role": "user", "content": user_input})
                messages.append({"role": "assistant", "content": f"I will use {tool_name}."})
                messages.append({"role": "tool", "content": str(result), "name": tool_name}) # OpenAI format roughly

                stream = await self.llm.generate(messages, stream=True, provider="deepseek")

                async for chunk in stream:
                    if hasattr(chunk, 'choices') and chunk.choices:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            yield {"status": "final_stream", "content": delta.content}
                            final_response += delta.content

            except Exception as e:
                final_response = f"Error executing tool {tool_name}: {e}"
                yield {"status": "final", "content": final_response}

        elif action == "CREATE_PLAN":
            yield {"status": "thinking", "message": "Creating plan..."}

            try:
                plan = await self.planner.create_plan(user_input, history, tools)
                yield {"status": "plan_created", "plan": [t.to_dict() for t in plan.tasks.values()]}

                # Execute Plan
                yield {"status": "executing", "message": "Executing plan..."}
                execution_result = await self.executor.execute_graph(plan, context)

                yield {"status": "observation", "result": str(execution_result)}

                # Generate final response
                yield {"status": "thinking", "message": "Finalizing..."}

                messages = list(history)
                messages.append({"role": "user", "content": user_input})
                messages.append({"role": "assistant", "content": "I have executed the plan."})
                messages.append({"role": "system", "content": f"Plan Execution Result: {execution_result}"})

                stream = await self.llm.generate(messages, stream=True, provider="deepseek")

                async for chunk in stream:
                    if hasattr(chunk, 'choices') and chunk.choices:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            yield {"status": "final_stream", "content": delta.content}
                            final_response += delta.content

            except Exception as e:
                final_response = f"Planning failed: {e}"
                yield {"status": "final", "content": final_response}

        else:
            final_response = "I am not sure what to do."
            yield {"status": "final", "content": final_response}

        # 4. Save Memory
        if final_response:
            await self.episodic_memory.add_message(chat_id, "user", user_input)
            await self.episodic_memory.add_message(chat_id, "assistant", final_response)

            # Optional: Add to vector memory if significant?
            # self.vector_memory.add(f"User: {user_input}\nAssistant: {final_response}")

        yield {"status": "final", "content": final_response}

    async def _execute_tool_safe(self, tool_name, args, context):
        """Executes a tool handling async/sync and errors."""
        is_async = self.module_manager.tool_metadata.get(tool_name, {}).get("is_async", False)

        if is_async:
            result = await self.module_manager.execute(tool_name, tool_context=context, **args)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        else:
            return await asyncio.to_thread(self.module_manager.execute, tool_name, tool_context=context, **args)
