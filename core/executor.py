import asyncio
from core.task_graph import TaskGraph, TaskStatus
from core.module_manager import ModuleManager

class Executor:
    def __init__(self, module_manager: ModuleManager):
        self.module_manager = module_manager

    async def execute_graph(self, graph: TaskGraph, context: dict = None):
        """
        Executes the task graph until completion or failure.
        Returns the result of the last completed task.
        """
        if not context:
            context = {}

        results = {} # task_id -> result

        while not graph.is_complete():
            ready_tasks = graph.get_ready_tasks()

            if not ready_tasks:
                # Deadlock or finished?
                if all(t.status in [TaskStatus.COMPLETED, TaskStatus.FAILED] for t in graph.tasks.values()):
                    break
                else:
                    return "Error: Plan stalled (dependency loop or failure)."

            # Execute ready tasks (could be parallelized)
            for task in ready_tasks:
                task.status = TaskStatus.RUNNING

                # Resolve arguments (replace placeholders if any)
                # Simple logic: If an argument is a string starting with '$', look up dependency result
                # Ideally, the planner should handle this via specific syntax, but let's keep it simple.
                # Or, we just pass the previous results in context?

                # For now, pass all previous results in a special arg if tool supports it?
                # Better: Update args with dependency results if explicitly referenced?

                # Simple implementation: Just execute.

                print(f"Executing task {task.id}: {task.tool} args={task.args}")

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

                except Exception as e:
                    graph.mark_failed(task.id, str(e))
                    return f"Task {task.id} ({task.tool}) failed: {e}"

        # Return the result of the last task (or all results?)
        # Usually the last added task is the goal.
        # Let's find the task with no dependents? or simply the last one by ID logic?
        # We'll return the last executed result.
        if results:
            return list(results.values())[-1]
        return "No tasks executed."
