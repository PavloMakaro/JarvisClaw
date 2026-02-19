import asyncio
import os
import sys
import shutil

# Add project root to path
sys.path.append(os.getcwd())

from core.memory.vector_memory import VectorMemory
from core.memory.episodic_memory import EpisodicMemory

async def test_components():
    print("Testing Components...")

    # 1. Vector Memory
    print("\n[VectorMemory]")
    # Clean up test file
    if os.path.exists("data/test_vector.json"):
        os.remove("data/test_vector.json")

    vm = VectorMemory("data/test_vector.json")
    vm.add("The capital of France is Paris.")
    vm.add("The capital of Germany is Berlin.")
    vm.add("Python is a programming language.")

    results = vm.search("France capital")
    print(f"Search 'France capital': {len(results)} results")
    if results and "France" in results[0]["text"]:
        print("OK: Found correct memory")
    else:
        print("FAIL: Search failed")

    # 2. Episodic Memory
    print("\n[EpisodicMemory]")
    # Clean up test file
    if os.path.exists("data/test_sessions.json"):
        os.remove("data/test_sessions.json")

    em = EpisodicMemory("data/test_sessions.json")
    await em.add_message("123", "user", "Hello")
    hist = await em.get_history("123")
    print(f"History for 123: {len(hist)} messages")

    if len(hist) == 1 and hist[0]["content"] == "Hello":
        print("OK: History saved/loaded")
    else:
        print("FAIL: History mismatch")

    # 3. UI Manager (Import check only as it requires a bot instance)
    print("\n[TelegramUIManager]")
    try:
        from core.ui.telegram_ui import TelegramUIManager
        print("OK: Import successful")
    except ImportError as e:
        print(f"FAIL: Import failed {e}")

if __name__ == "__main__":
    asyncio.run(test_components())
