from typing import List, Dict, Any, Optional
import uuid
import enum

class TaskStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class Task:
    def __init__(self, tool: str, args: Dict[str, Any], dependencies: List[str] = None, task_id: str = None):
        self.id = task_id or str(uuid.uuid4())[:8]
        self.tool = tool
        self.args = args
        self.dependencies = dependencies or []
        self.status = TaskStatus.PENDING
        self.result = None
        self.error = None

    def to_dict(self):
        return {
            "id": self.id,
            "tool": self.tool,
            "args": self.args,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "result": self.result
        }

class TaskGraph:
    def __init__(self, tasks: List[Task] = None):
        self.tasks = {t.id: t for t in (tasks or [])}

    def add_task(self, task: Task):
        self.tasks[task.id] = task

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)

    def get_ready_tasks(self) -> List[Task]:
        """Returns tasks that are PENDING and have all dependencies COMPLETED."""
        ready = []
        for task in self.tasks.values():
            if task.status != TaskStatus.PENDING:
                continue

            deps_met = True
            for dep_id in task.dependencies:
                dep_task = self.tasks.get(dep_id)
                if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                    deps_met = False
                    break

            if deps_met:
                ready.append(task)
        return ready

    def mark_completed(self, task_id: str, result: Any):
        if task_id in self.tasks:
            self.tasks[task_id].status = TaskStatus.COMPLETED
            self.tasks[task_id].result = result

    def mark_failed(self, task_id: str, error: str):
        if task_id in self.tasks:
            self.tasks[task_id].status = TaskStatus.FAILED
            self.tasks[task_id].error = error

    def is_complete(self):
        return all(t.status == TaskStatus.COMPLETED for t in self.tasks.values())
