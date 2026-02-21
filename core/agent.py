import asyncio
import logging
import json
from typing import Dict, Any, AsyncGenerator, List

from core.llm import LLMService
from core.module_manager import ModuleManager
from core.memory.vector_memory import VectorMemory
from core.memory.episodic_memory import EpisodicMemory
# from core.decision import DecisionLayer # Removed, integrated into loop
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

        # self.decision_layer = DecisionLayer(self.llm) # Deprecated
        self.planner = Planner(self.llm)
        self.executor = Executor(self.module_manager)

        self.logger = logging.getLogger("Agent")

        # Load system prompt
        self.system_prompt = (
            "You are GarvisClaw, an advanced AI agent. "
            "You have access to tools and a planning module. "
            "When solving complex tasks, first create a plan using 'create_plan'. "
            "Think step-by-step. "
            "Output your reasoning before taking actions."
        )
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
        Main execution loop (ReAct style).
        Yields status updates and final response.
        """
        if context is None:
            context = {}

        # 1. Load History
        history = await self.episodic_memory.get_history(chat_id)

        # 2. Get Tool Definitions
        tools_definitions = self.module_manager.get_definitions()

        # Ensure correct OpenAI format
        formatted_tools = []
        for t in tools_definitions:
            if "type" not in t:
                formatted_tools.append({"type": "function", "function": t})
            else:
                formatted_tools.append(t)

        # Add Planner Tool definition manually if not present
        # (Assuming Planner isn't in ModuleManager yet, or if it is, this duplicates but that's ok to check)
        # Actually, let's just rely on ModuleManager tools, but if we want explicit planning:
        # We can implement 'create_plan' handling inside the tool execution block.
        # Let's add it to formatted_tools explicitly.

        plan_tool_def = {
            "type": "function",
            "function": {
                "name": "create_plan",
                "description": "Create a step-by-step execution plan for complex tasks.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string", "description": "Description of the task to plan for."}
                    },
                    "required": ["description"]
                }
            }
        }
        # Check if already exists
        if not any(t["function"]["name"] == "create_plan" for t in formatted_tools):
            formatted_tools.append(plan_tool_def)

        # 3. Initial Messages
        # Ensure system prompt is first for caching
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        step = 0
        max_steps = 30 # Safety limit

        while step < max_steps:
            step += 1
            yield {"status": "thinking", "step": step}

            # Call LLM with Streaming
            response_content = ""
            tool_calls_buffer = [] # To reconstruct tool calls from chunks

            # We need to handle the stream carefully
            # The LLMService.generate returns a generator
            try:
                stream = await self.llm.generate(messages, tools=formatted_tools, stream=True, provider="deepseek")

                # State for tool call reconstruction
                current_tool_index = -1

                async for chunk in stream:
                    # Error handling (string error)
                    if isinstance(chunk, str):
                        # This usually means an error occurred in LLMService
                        yield {"status": "final", "content": chunk}
                        return

                    if hasattr(chunk, 'choices') and chunk.choices:
                        delta = chunk.choices[0].delta

                        # 1. Content (Reasoning/Thought)
                        if delta.content:
                            response_content += delta.content
                            yield {"status": "thinking", "thought": response_content, "step": step}

                        # 2. Tool Calls
                        if delta.tool_calls:
                            for tc in delta.tool_calls:
                                if tc.index is not None and tc.index != current_tool_index:
                                    # New tool call started
                                    current_tool_index = tc.index
                                    tool_calls_buffer.append({
                                        "id": tc.id or "",
                                        "type": "function",
                                        "function": {"name": tc.function.name or "", "arguments": tc.function.arguments or ""}
                                    })
                                else:
                                    # Append to current tool call
                                    if current_tool_index >= 0 and current_tool_index < len(tool_calls_buffer):
                                        if tc.function.name:
                                            tool_calls_buffer[current_tool_index]["function"]["name"] += tc.function.name
                                        if tc.function.arguments:
                                            tool_calls_buffer[current_tool_index]["function"]["arguments"] += tc.function.arguments

            except Exception as e:
                self.logger.error(f"LLM Generation failed: {e}")
                yield {"status": "final", "content": f"Error: {e}"}
                return

            # Analyze Result
            # If no tool calls and we have content, it's likely the final answer or a question.
            # But we must check if the model intended to stop.

            # If we have tool calls, execute them.
            if tool_calls_buffer:
                # Add Assistant Message with Tool Calls to history
                # We need to construct the full assistant message object
                # DeepSeek/OpenAI expects the 'tool_calls' field

                # Fix up tool calls (arguments are strings, need parse?)
                # Actually, for the history, we keep them as objects/dicts

                assistant_msg = {
                    "role": "assistant",
                    "content": response_content,
                    "tool_calls": tool_calls_buffer
                }
                messages.append(assistant_msg)

                # Execute each tool
                for tc in tool_calls_buffer:
                    func_name = tc["function"]["name"]
                    args_str = tc["function"]["arguments"]
                    call_id = tc["id"] or "call_" + func_name

                    try:
                        args = json.loads(args_str)
                    except:
                        args = {} # Error parsing args

                    yield {"status": "tool_use", "tool_call": {"name": func_name, "args": args}}

                    # SPECIAL HANDLING: create_plan
                    if func_name == "create_plan":
                        # Call planner
                        try:
                            # Planner.create_plan expects (user_input, history, tools)
                            # But here we are in a loop. We might just use the args description.
                            plan_desc = args.get("description", user_input)

                            # Using the existing Planner logic
                            # We need to adapt it.
                            # Let's just create a new plan based on the description
                            # The Planner class currently uses LLM to generate a plan.
                            plan_graph = await self.planner.create_plan(plan_desc, history, tools_definitions)

                            plan_data = [t.to_dict() for t in plan_graph.tasks.values()]
                            result_str = f"Plan created with {len(plan_data)} steps."

                            yield {"status": "plan_created", "plan": plan_data}

                            # Optionally execute the plan automatically?
                            # The user said "make AI determine steps".
                            # If we have a plan, maybe we just return it as observation?
                            # Or we can use `executor` to run it?
                            # Let's return it as observation so the Agent knows the plan exists.
                            result_str = json.dumps(plan_data)

                        except Exception as e:
                            result_str = f"Planning Error: {e}"

                    else:
                        # Standard Tool
                        try:
                            result = await self._execute_tool_safe(func_name, args, context)
                            result_str = str(result)
                        except Exception as e:
                            result_str = f"Error: {e}"

                    yield {"status": "observation", "observation": result_str}

                    # Append Tool Output to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id, # Must match
                        "name": func_name,
                        "content": result_str
                    })

                # Loop continues to next step (Agent reflects on Tool Outputs)

            else:
                # No tool calls. This is the Final Answer.
                yield {"status": "final_stream", "content": response_content} # It was already streamed as 'thought' effectively, but let's signal finality.

                # Wait, if response_content was just "I will check..." and then no tool call?
                # That happens if model fails to call tool.
                # But if it's "The answer is 42", we are done.

                # We yield 'final' with the full content to ensure UI knows we are done.
                yield {"status": "final", "content": response_content}

                # Save to memory
                await self.episodic_memory.add_message(chat_id, "user", user_input)
                await self.episodic_memory.add_message(chat_id, "assistant", response_content)
                break

    async def _execute_tool_safe(self, tool_name, args, context):
        """Executes a tool handling async/sync and errors."""
        # Check if tool exists in module manager
        if tool_name not in self.module_manager.tools:
            return f"Tool {tool_name} not found."

        is_async = self.module_manager.tool_metadata.get(tool_name, {}).get("is_async", False)

        if is_async:
            result = await self.module_manager.execute(tool_name, tool_context=context, **args)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        else:
            return await asyncio.to_thread(self.module_manager.execute, tool_name, tool_context=context, **args)
