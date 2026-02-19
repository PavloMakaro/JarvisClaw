import sys
import os
import asyncio

# Add project root to path
sys.path.append(os.getcwd())

from core.module_manager import ModuleManager

async def test_manager():
    print("Testing ModuleManager...")
    manager = ModuleManager()
    manager.load_modules()

    print("\nLoaded Modules:", manager.modules.keys())

    # Check if datetime module is loaded
    if "datetime" not in manager.modules:
        print("FAIL: datetime module not loaded")
        return

    # Check if tools are registered
    tools = ["get_current_time", "get_irkutsk_time", "get_weather"]
    for t in tools:
        if t not in manager.tools:
            print(f"FAIL: tool {t} not registered")
        else:
            print(f"OK: tool {t} registered")

    # Execute a tool
    print("\nExecuting get_current_time...")
    result = await manager.execute("get_current_time")
    if asyncio.iscoroutine(result):
        result = await result
    print("Result:", result)

    if "Error" in str(result):
         print("FAIL: Tool execution error")
    else:
         print("OK: Tool executed successfully")

    # Check definitions
    print("\nChecking definitions...")
    defs = manager.get_definitions()
    print(f"Found {len(defs)} definitions")
    if len(defs) >= 3:
        print("OK: Definitions found")
    else:
        print("FAIL: Not enough definitions")

if __name__ == "__main__":
    asyncio.run(test_manager())
