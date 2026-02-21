import asyncio
from typing import AsyncGenerator, Dict, Any
from core.task_graph import TaskGraph, TaskStatus
from core.module_manager import ModuleManager

class Executor:
    def __init__(self, module_manager: ModuleManager):
        self.module_manager = module_manager

    async def execute_graph(self, graph: TaskGraph, context: dict = None):
        """
        Executes the task graph until completion or failure.
        Returns the result of the last completed task.
        Legacy method for backward compatibility.
        """
        last_result = None
        async for event in self.execute_graph_generator(graph, context):
            if event["status"] == "task_complete":
                last_result = event["result"]
            elif event["status"] == "error":
                return event["message"]
        return last_result

    async def execute_graph_generator(self, graph: TaskGraph, context: dict = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executes the task graph and yields events.
        Events:
        - {"status": "task_start", "task": task_obj}
        - {"status": "task_complete", "task": task_obj, "result": result}
        - {"status": "task_failed", "task": task_obj, "error": error}
        - {"status": "plan_complete", "result": final_result}
        """
        if not context:
            context = {}

        results = {} # task_id -> result

        loop_count = 0
        max_loops = 50 # Safety break

        while not graph.is_complete() and loop_count < max_loops:
            loop_count += 1
            ready_tasks = graph.get_ready_tasks()

            if not ready_tasks:
                # Deadlock or finished?
                if all(t.status in [TaskStatus.COMPLETED, TaskStatus.FAILED] for t in graph.tasks.values()):
                    break
                else:
                    yield {"status": "error", "message": "Plan stalled (dependency loop or failure)."}
                    return

            # Execute ready tasks (sequentially for now to keep generator simple)
            for task in ready_tasks:
                task.status = TaskStatus.RUNNING
                yield {"status": "task_start", "task": task.to_dict()}

                # Resolve arguments
                # (Simple arg resolution could be added here if needed)

                try:
                    # Check if async
                    is_async = self.module_manager.tool_metadata.get(task.tool, {}).get("is_async", False)

                    if is_async:
                        result = await self.module_manager.execute(task.tool, tool_context=context, **task.args)
                        if asyncio.iscoroutine(result):
                            result = await result
                    else:
                        result = await asyncio.to_thread(self.module_manager.execute, task.tool, tool_context=context, **task.args)

                    graph.mark_completed(task.id, result)
                    results[task.id] = result
                    yield {"status": "task_complete", "task": task.to_dict(), "result": str(result)}

                except Exception as e:
                    graph.mark_failed(task.id, str(e))
                    yield {"status": "task_failed", "task": task.to_dict(), "error": str(e)}
                    # Continue or break? Usually break on failure unless handled
                    # For now, let's continue if possible, but usually dependency checks will stop subsequent tasks.

        # Return the result of the last task
        if results:
            final_result = list(results.values())[-1]
            yield {"status": "plan_complete", "result": final_result}
        else:
            yield {"status": "plan_complete", "result": "No tasks executed."}
