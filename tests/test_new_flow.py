import asyncio
import sys
import os
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Add project root to path
sys.path.append(os.getcwd())

# We need to import Agent, but we want to patch its dependencies before instantiation
# However, we can patch the class references in core.agent module context or patch where they are used.
from core.agent import Agent
from core.task_graph import TaskGraph, Task

class TestAgentNewFlow(unittest.TestCase):
    def setUp(self):
        # Patch dependencies
        self.vm_patcher = patch('core.agent.VectorMemory')
        self.em_patcher = patch('core.agent.EpisodicMemory')
        self.llm_patcher = patch('core.agent.LLMService')

        self.MockVM = self.vm_patcher.start()
        self.MockEM = self.em_patcher.start()
        self.MockLLM = self.llm_patcher.start()

        # Setup mock instances
        self.mock_llm_instance = self.MockLLM.return_value
        self.mock_llm_instance.generate = AsyncMock()

        # Mock generator for LLM stream
        async def mock_stream(*args, **kwargs):
            yield "Mock response"
        self.mock_llm_instance.generate.side_effect = mock_stream

        self.mock_em_instance = self.MockEM.return_value
        self.mock_em_instance.get_history = AsyncMock(return_value=[])
        self.mock_em_instance.add_message = AsyncMock()

        self.mock_vm_instance = self.MockVM.return_value
        self.mock_vm_instance.add = MagicMock()

        # Instantiate Agent (now uses mocks)
        self.agent = Agent()

        # We also need to ensure DecisionLayer and Planner use the mock LLM
        # Agent init: self.decision_layer = DecisionLayer(self.llm)
        # Since self.llm is the mock instance, it should be fine.

    def tearDown(self):
        self.vm_patcher.stop()
        self.em_patcher.stop()
        self.llm_patcher.stop()

    def test_simple_tool_loop(self):
        """Test loop: Use Tool -> Respond"""
        print("\n--- Testing Simple Tool Loop ---")

        # Mock Decision Layer decision
        async def mock_decide(user_input, history, tools):
            # Check history to see if tool was used
            # We need to check if ANY message in history is a tool observation
            # Note: history passed to decide is list of dicts.

            # Since we append to history in the loop, we can check it.
            has_tool_output = False
            for m in history:
                if m.get("role") == "user" and "Observation" in m.get("content", ""):
                    has_tool_output = True
                    break

            if has_tool_output:
                return {"decision": "RESPOND_DIRECTLY"}
            else:
                return {"decision": "USE_TOOL", "tool_name": "dummy_tool", "tool_args": {"arg": "val"}}

        self.agent.decision_layer.decide = mock_decide

        # Register dummy tool directly to module manager
        self.agent.module_manager.modules["dummy_tool"] = MagicMock() # Placeholder

        def dummy_func(arg):
            return f"Result: {arg}"

        self.agent.module_manager.tool_metadata["dummy_tool"] = {
            "name": "dummy_tool",
            "func": dummy_func,
            "description": "A dummy tool",
            "is_async": False
        }

        # Mock execute
        self.agent.module_manager.execute = MagicMock(return_value="Dummy Tool Result")

        async def run_test():
            events = []
            async for update in self.agent.run("Do something", "test_chat"):
                events.append(update["status"])
                if update["status"] == "tool_use":
                    print(f"Tool used: {update['tool']}")
                elif update["status"] == "observation":
                    print(f"Observation: {update['result']}")

            # Verify flow
            self.assertIn("thinking", events)
            self.assertIn("tool_use", events)
            self.assertIn("observation", events)
            self.assertIn("final_stream", events)
            self.assertIn("final", events)
            print("Simple loop success!")

        asyncio.run(run_test())

    def test_plan_mode(self):
        """Test loop: Create Plan -> Execute Plan -> Respond"""
        print("\n--- Testing Plan Mode ---")

        # Mock Decision Layer
        # 1. CREATE_PLAN
        # 2. RESPOND_DIRECTLY
        call_count = 0
        async def mock_decide(user_input, history, tools):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"decision": "CREATE_PLAN"}
            else:
                return {"decision": "RESPOND_DIRECTLY"}

        self.agent.decision_layer.decide = mock_decide

        # Mock Planner
        async def mock_create_plan(*args):
            graph = TaskGraph()
            task = Task(tool="dummy_tool", args={"arg": "plan_val"}, task_id="1")
            graph.add_task(task)
            return graph

        self.agent.planner.create_plan = mock_create_plan

        # Register dummy tool
        self.agent.module_manager.modules["dummy_tool"] = MagicMock()

        def dummy_func_plan(arg):
            return f"Plan Result: {arg}"

        self.agent.module_manager.tool_metadata["dummy_tool"] = {
            "name": "dummy_tool",
            "func": dummy_func_plan,
            "description": "A dummy tool",
            "is_async": False
        }
        self.agent.module_manager.execute = MagicMock(return_value="Plan Tool Result")

        async def run_test():
            events = []
            async for update in self.agent.run("Make a plan", "test_chat"):
                events.append(update["status"])
                if update["status"] == "plan_created":
                    print("Plan created")
                elif update["status"] == "executing":
                    print("Executing plan")
                elif update["status"] == "observation":
                    print(f"Observation: {update['result']}")

            # Verify flow
            self.assertIn("plan_created", events)
            self.assertIn("executing", events)
            self.assertIn("tool_use", events)
            self.assertIn("observation", events)
            self.assertIn("final", events)
            print("Plan mode success!")

        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()
