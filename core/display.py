from typing import List, Dict, Any, Optional
import json

class DisplayManager:
    def __init__(self):
        self.step_count = 0
        self.thought = ""
        self.plan = []
        self.current_tool = None
        self.tool_output = None

    def update(self, update_data: Dict[str, Any]):
        """
        Updates the internal state based on the update_data dictionary.
        Expected keys: 'step', 'thought', 'plan', 'tool_call', 'observation'.
        """
        if "step" in update_data:
            self.step_count = update_data["step"]

        if "thought" in update_data:
            self.thought = update_data["thought"]

        if "plan" in update_data:
            # Plan can be a list of Task objects or dicts
            raw_plan = update_data["plan"]
            if isinstance(raw_plan, list):
                self.plan = []
                for item in raw_plan:
                    if hasattr(item, "to_dict"):
                        self.plan.append(item.to_dict())
                    elif isinstance(item, dict):
                        self.plan.append(item)
                    else:
                        self.plan.append({"task": str(item), "status": "unknown"})
            # If it's a TaskGraph object
            elif hasattr(raw_plan, "tasks"):
                self.plan = [t.to_dict() for t in raw_plan.tasks.values()]

        if "tool_call" in update_data:
            self.current_tool = update_data["tool_call"]
            self.tool_output = None # Clear previous output

        if "observation" in update_data:
            self.tool_output = update_data["observation"]

    def render(self) -> str:
        """Renders the current state as a formatted Markdown string."""
        parts = []

        # Header
        header = f"🧠 **Thinking Process**"
        if self.step_count > 0:
            header += f" (Step {self.step_count})"
        parts.append(header)

        # Plan Visualization
        if self.plan:
            parts.append("\n📋 **Plan**")
            for task in self.plan:
                t_id = task.get("id", "?")
                # Handle different task structures
                tool_name = task.get("tool", "")
                args = task.get("args", {})
                status = task.get("status", "pending")

                icon = "⬜"
                if status == "done" or status == "completed": icon = "✅"
                elif status == "running": icon = "⏳"
                elif status == "failed": icon = "❌"

                desc = f"{tool_name}"
                if args:
                    # simplistic args display
                    desc += f"({list(args.keys())})"

                parts.append(f"{icon} `{t_id}` {desc}")

        # Current Thought
        if self.thought:
            parts.append(f"\n🤔 **Thought**")
            parts.append(f"> {self.thought}")

        # Active Tool
        if self.current_tool:
            parts.append(f"\n🛠 **Tool Call**")
            name = self.current_tool.get("name", "Unknown")
            args = self.current_tool.get("args", {})
            try:
                args_str = json.dumps(args, ensure_ascii=False)
            except:
                args_str = str(args)

            parts.append(f"`{name}`")
            parts.append(f"Args: `{args_str}`")

        # Observation (Result)
        if self.tool_output:
            parts.append(f"\n👀 **Observation**")
            out_str = str(self.tool_output)
            # Truncate strictly for Telegram limits (4096 chars total)
            # We reserve space for other parts, so truncate observation to ~2000 chars
            if len(out_str) > 2000:
                out_str = out_str[:1997] + "..."

            # Wrap in code block
            parts.append(f"```\n{out_str}\n```")

        return "\n".join(parts)
