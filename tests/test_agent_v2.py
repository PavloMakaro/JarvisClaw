import asyncio
import sys
import os
sys.path.append(os.getcwd())

from core.agent import Agent

# Mock LLM Service injection to avoid API calls in test
class MockLLMService:
    async def generate(self, messages, provider="deepseek", stream=False, tools=None, tool_choice=None):
        if stream:
            async def gen():
                class Chunk:
                    class Choice:
                        class Delta:
                            content = "Mock response"
                            tool_calls = None
                        delta = Delta()
                    choices = [Choice()]
                yield Chunk()
            return gen()
        else:
            class Message:
                content = '{"decision": "RESPOND_DIRECTLY"}'
            return Message()

async def test_agent():
    print("Testing Agent V2...")

    agent = Agent()
    # Inject Mock LLM
    agent.llm = MockLLMService()
    # Also inject into decision layer/planner since they store reference
    agent.decision_layer.llm = agent.llm
    agent.planner.llm = agent.llm

    # Verify modules loaded
    print(f"\nLoaded Modules: {list(agent.module_manager.modules.keys())}")
    if "web_search" in agent.module_manager.modules:
        print("OK: web_search module loaded")
    else:
        print("FAIL: web_search module NOT loaded")

    print("\n[Running 'Hello']")
    async for update in agent.run("Hello", "test_user"):
        print(f"Update: {update['status']}")
        if update['status'] == 'final':
            print(f"Final: {update['content']}")

    # Test Tool Use path (requires mocking decision response to USE_TOOL)
    print("\n[Running 'What time is it?']")

    # Mock decision to USE_TOOL
    async def mock_decide(*args):
        return {"decision": "USE_TOOL", "tool_name": "get_current_time", "tool_args": {}}
    agent.decision_layer.decide = mock_decide

    async for update in agent.run("What time is it?", "test_user"):
         print(f"Update: {update['status']}")
         if update['status'] == 'tool_use':
             print(f"Tool: {update['tool']}")
         if update['status'] == 'final':
             print(f"Final: {update['content']}")

if __name__ == "__main__":
    asyncio.run(test_agent())
