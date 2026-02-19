from typing import List, Dict, Any
import json
import uuid
from core.task_graph import TaskGraph, Task

class Planner:
    def __init__(self, llm_service):
        self.llm = llm_service

    async def create_plan(self, user_input: str, history: List[Dict], available_tools: List[Dict]) -> TaskGraph:
        """
        Generates a TaskGraph for the user request.
        """

        tool_definitions = json.dumps(available_tools, indent=2)

        system_prompt = f"""
You are the Planner of an AI agent.
Create a step-by-step execution plan to solve the user's request.

AVAILABLE TOOLS:
{tool_definitions}

OUTPUT FORMAT (JSON ONLY):
[
  {{
    "id": "1",
    "tool": "tool_name",
    "args": {{ "arg_name": "value" }},
    "dependencies": []
  }},
  {{
    "id": "2",
    "tool": "another_tool",
    "args": {{ "input": "value from task 1" }},
    "dependencies": ["1"]
  }}
]

RULES:
1. Use only available tools.
2. Ensure dependencies are correct (a task depending on another task's output must list its ID in 'dependencies').
3. Keep the plan efficient.
4. If you need to answer a question after gathering data, use a final task (if a "final_answer" tool exists) or just return the data.
   (Note: For this system, the last task's output is usually the answer).
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context: {history[-3:] if history else []}\nRequest: {user_input}"}
        ]

        try:
            response = await self.llm.generate(
                messages,
                provider="deepseek",
                stream=False
            )

            content = response.content
            # Clean up markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            plan_data = json.loads(content)

            graph = TaskGraph()
            for task_def in plan_data:
                task = Task(
                    tool=task_def["tool"],
                    args=task_def.get("args", {}),
                    dependencies=task_def.get("dependencies", []),
                    task_id=task_def.get("id")
                )
                graph.add_task(task)

            return graph

        except Exception as e:
            print(f"Planning error: {e}")
            return TaskGraph() # Return empty graph on failure
