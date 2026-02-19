import asyncio
import sys
import os
sys.path.append(os.getcwd())

from core.planner import Planner
from core.executor import Executor
from core.module_manager import ModuleManager
from core.task_graph import TaskGraph, Task

# Mock LLM for Planner
class MockLLM:
    async def generate(self, messages, provider="deepseek", stream=False):
        class Message:
            content = '[\n  {\n    "id": "1",\n    "tool": "get_current_time",\n    "args": {},\n    "dependencies": []\n  }\n]'
        return Message()

async def test_execution():
    print("Testing Planner & Executor...")

    # Setup
    manager = ModuleManager()
    manager.load_modules() # Should load datetime

    llm = MockLLM()
    planner = Planner(llm)
    executor = Executor(manager)

    # 1. Test Planner (Mocked)
    print("\n[Planner]")
    tools = manager.get_definitions()
    graph = await planner.create_plan("What time is it?", [], tools)

    if len(graph.tasks) == 1:
        print("OK: Plan generated with 1 task")
    else:
        print(f"FAIL: Plan generation failed, tasks={len(graph.tasks)}")

    # 2. Test Executor
    print("\n[Executor]")
    # We use the generated graph
    result = await executor.execute_graph(graph)
    print("Execution Result:", result)

    if "Error" not in str(result) and ":" in str(result): # Expecting a time string like "2026-..."
        print("OK: Execution successful")
    else:
        print("FAIL: Execution failed")

if __name__ == "__main__":
    asyncio.run(test_execution())
