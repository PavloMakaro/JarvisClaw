import asyncio
import logging
import json
from typing import Dict, Any, AsyncGenerator, List

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
        current_history = list(history) # Working copy for this session

        # 2. Get Tool Definitions
        tools = self.module_manager.get_definitions()

        yield {"status": "thinking", "message": "Analyzing request..."}

        loop_count = 0
        max_loops = 20 # Safety limit, though user asked to remove strict limits, we need *some* break.

        final_response = ""

        while loop_count < max_loops:
            loop_count += 1

            # Decision Layer
            try:
                decision = await self.decision_layer.decide(user_input, current_history, tools)
                self.logger.info(f"Decision for {chat_id} (Loop {loop_count}): {decision}")
            except Exception as e:
                self.logger.error(f"Decision failed: {e}")
                # Fallback
                decision = {"decision": "RESPOND_DIRECTLY"}

            action = decision.get("decision")

            if action == "RESPOND_DIRECTLY":
                yield {"status": "thinking", "message": "Drafting response..."}

                messages = list(current_history)
                messages.append({"role": "user", "content": user_input})

                # Add system prompt if needed
                if not messages or messages[0]["role"] != "system":
                     messages.insert(0, {"role": "system", "content": self.system_prompt})

                stream = await self.llm.generate(messages, stream=True, provider="deepseek")

                async for chunk in stream:
                    if isinstance(chunk, str):
                        yield {"status": "final_stream", "content": chunk}
                        final_response += chunk
                    elif hasattr(chunk, 'choices') and chunk.choices:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            yield {"status": "final_stream", "content": delta.content}
                            final_response += delta.content

                # Break loop after responding
                break

            elif action == "USE_TOOL":
                tool_name = decision.get("tool_name")
                tool_args = decision.get("tool_args", {})

                yield {"status": "tool_use", "tool": tool_name, "args": tool_args}

                # Execute tool
                try:
                    result = await self._execute_tool_safe(tool_name, tool_args, context)
                    yield {"status": "observation", "result": str(result)}

                    # Update history
                    current_history.append({"role": "assistant", "content": f"I will use {tool_name}."})
                    current_history.append({"role": "user", "content": f"Observation from {tool_name}: {str(result)}"})

                    # Continue loop to see if we need more tools or response
                    yield {"status": "thinking", "message": "Evaluating result..."}

                except Exception as e:
                    yield {"status": "error", "message": f"Tool execution failed: {e}"}
                    # Decide whether to continue or stop? Let's stop to be safe or try to explain.
                    final_response = f"I encountered an error executing {tool_name}: {e}"
                    yield {"status": "final", "content": final_response}
                    break

            elif action == "CREATE_PLAN":
                yield {"status": "thinking", "message": "Creating plan..."}

                try:
                    plan = await self.planner.create_plan(user_input, current_history, tools)

                    # Log plan
                    plan_steps = [t.to_dict() for t in plan.tasks.values()]
                    yield {"status": "plan_created", "plan": plan_steps}

                    # Execute Plan
                    yield {"status": "executing", "message": "Executing plan..."}

                    execution_result = None
                    async for event in self.executor.execute_graph_generator(plan, context):
                        if event["status"] == "task_start":
                             yield {"status": "tool_use", "tool": event["task"]["tool"], "args": event["task"]["args"]}
                        elif event["status"] == "task_complete":
                             yield {"status": "observation", "result": event["result"]}
                        elif event["status"] == "plan_complete":
                             execution_result = event["result"]
                             yield {"status": "observation", "result": f"Plan completed. Result: {execution_result}"}

                    # Update history
                    current_history.append({"role": "assistant", "content": "I have executed the plan."})
                    current_history.append({"role": "user", "content": f"Plan Execution Result: {execution_result}"})

                    # Continue loop
                    yield {"status": "thinking", "message": "Evaluating plan result..."}

                except Exception as e:
                    final_response = f"Planning execution failed: {e}"
                    yield {"status": "final", "content": final_response}
                    break

            else:
                # Unknown action
                final_response = "I am not sure what to do."
                yield {"status": "final", "content": final_response}
                break

        # 4. Save Memory (at the end)
        if final_response:
            await self.episodic_memory.add_message(chat_id, "user", user_input)
            await self.episodic_memory.add_message(chat_id, "assistant", final_response)

            # Add to vector memory (LanceDB)
            try:
                self.vector_memory.add(f"User: {user_input}\nAssistant: {final_response}")
            except Exception as e:
                self.logger.warning(f"Failed to add to vector memory: {e}")

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
