import asyncio
import sys
import os
sys.path.append(os.getcwd())

from core.task_graph import TaskGraph, Task, TaskStatus
from core.decision import DecisionLayer

# Mock LLM Service
class MockLLM:
    async def generate(self, messages, provider="deepseek", stream=False):
        class Message:
            content = '{"decision": "USE_TOOL", "tool_name": "get_current_time", "tool_args": {}, "reasoning": "User asked for time"}'
        return Message()

async def test_decision_layer():
    print("Testing Decision Layer & Task Graph...")

    # 1. Test Task Graph
    print("\n[TaskGraph]")
    tg = TaskGraph()
    t1 = Task("search", {"query": "foo"}, task_id="1")
    t2 = Task("summarize", {"text": "foo"}, dependencies=["1"], task_id="2")

    tg.add_task(t1)
    tg.add_task(t2)

    ready = tg.get_ready_tasks()
    print(f"Ready tasks: {[t.id for t in ready]}")
    if len(ready) == 1 and ready[0].id == "1":
        print("OK: Dependency resolution works")
    else:
        print("FAIL: Dependency resolution failed")

    tg.mark_completed("1", "search_result")
    ready = tg.get_ready_tasks()
    print(f"Ready tasks after t1 complete: {[t.id for t in ready]}")
    if len(ready) == 1 and ready[0].id == "2":
        print("OK: Next task ready")
    else:
        print("FAIL: Next task not ready")

    # 2. Test Decision Layer
    print("\n[DecisionLayer]")
    llm = MockLLM()
    decision_layer = DecisionLayer(llm)

    result = await decision_layer.decide(
        "What time is it?",
        [],
        [{"function": {"name": "get_current_time"}}]
    )

    print("Decision result:", result)
    if result["decision"] == "USE_TOOL" and result["tool_name"] == "get_current_time":
        print("OK: Decision parsing works")
    else:
        print("FAIL: Decision parsing failed")

if __name__ == "__main__":
    asyncio.run(test_decision_layer())
