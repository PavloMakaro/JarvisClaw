import os
import json
import importlib.util
import inspect
import glob
import sys
import traceback

class RegistryAdapter:
    def __init__(self, manager):
        self.manager = manager

    def register(self, name, func, description, requires_context=False):
        # Determine if async
        is_async = inspect.iscoroutinefunction(func)

        # Register tool in manager
        self.manager.tools[name] = func
        self.manager.tool_metadata[name] = {
            "name": name,
            "func": func,
            "description": description,
            "is_async": is_async,
            "requires_context": requires_context
        }

class ModuleManager:
    def __init__(self, modules_dir="modules"):
        self.modules_dir = modules_dir
        self.modules = {}  # loaded modules metadata
        self.tools = {}    # map tool_name -> function
        self.tool_metadata = {} # map tool_name -> metadata
        self.descriptions = []

    def load_modules(self):
        """Scans the modules directory and loads all valid modules."""
        if not os.path.exists(self.modules_dir):
            os.makedirs(self.modules_dir)
            return

        # 1. Load directory-based modules (New Format)
        for item in os.listdir(self.modules_dir):
            module_path = os.path.join(self.modules_dir, item)
            if os.path.isdir(module_path):
                self._load_single_module(module_path, item)

        # 2. Load file-based modules (Legacy Format)
        for filepath in glob.glob(os.path.join(self.modules_dir, "*.py")):
            filename = os.path.basename(filepath)
            module_name = filename[:-3]
            if module_name == "__init__":
                continue

            self._load_legacy_module(filepath, module_name)

    def _load_single_module(self, path, module_name):
        """Loads a single module from a directory."""
        json_path = os.path.join(path, "module.json")
        tools_path = os.path.join(path, "tools.py")

        if not os.path.exists(json_path):
            return

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Load python module
            if os.path.exists(tools_path):
                spec = importlib.util.spec_from_file_location(f"modules.{module_name}", tools_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[f"modules.{module_name}"] = module
                    spec.loader.exec_module(module)

                    # Register tools
                    if "tools" in config:
                        for tool_name in config["tools"]:
                            if hasattr(module, tool_name):
                                func = getattr(module, tool_name)
                                self.register_tool(tool_name, func, config.get("description", ""))
                            else:
                                print(f"Warning: Tool '{tool_name}' defined in {json_path} but not found in {tools_path}")

            self.modules[module_name] = config
            print(f"Loaded module: {module_name}")

        except Exception as e:
            print(f"Error loading module {module_name}: {e}")
            traceback.print_exc()

    def _load_legacy_module(self, filepath, module_name):
        """Loads a legacy single-file module."""
        try:
            spec = importlib.util.spec_from_file_location(f"modules.{module_name}", filepath)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[f"modules.{module_name}"] = module
                spec.loader.exec_module(module)

                # Look for register_tools(registry)
                if hasattr(module, "register_tools"):
                    adapter = RegistryAdapter(self)
                    try:
                        module.register_tools(adapter)
                        self.modules[module_name] = {"type": "legacy", "name": module_name}
                        print(f"Loaded legacy module: {module_name}")
                    except Exception as e:
                        print(f"Error registering tools for legacy module {module_name}: {e}")
        except Exception as e:
            print(f"Error loading legacy module {module_name}: {e}")
            # Don't print stack trace for missing dependencies to reduce noise, just log error
            # traceback.print_exc()

    def register_tool(self, name, func, module_description):
        """Registers a tool function."""
        self.tools[name] = func

        # Extract docstring as description if available, otherwise use module description
        desc = func.__doc__.strip() if func.__doc__ else module_description

        self.tool_metadata[name] = {
            "name": name,
            "func": func,
            "description": desc,
            "is_async": inspect.iscoroutinefunction(func),
            "requires_context": False
        }

    def get_tool(self, name):
        return self.tools.get(name)

    def get_definitions(self):
        """Returns OpenAI-compatible tool definitions."""
        definitions = []
        for name, meta in self.tool_metadata.items():
            func = meta["func"]
            desc = meta["description"]

            # Simple parameter extraction (can be improved)
            try:
                sig = inspect.signature(func)
                properties = {}
                required = []

                for param_name, param in sig.parameters.items():
                    if param_name in ["self", "ctx", "context", "kwargs", "args", "registry", "bot", "job_queue", "chat_id"]:
                        continue

                    param_type = "string"
                    if param.annotation == int: param_type = "integer"
                    elif param.annotation == float: param_type = "number"
                    elif param.annotation == bool: param_type = "boolean"
                    elif param.annotation == list: param_type = "array"
                    elif param.annotation == dict: param_type = "object"

                    properties[param_name] = {"type": param_type}
                    if param.default == inspect.Parameter.empty:
                        required.append(param_name)

                definitions.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": desc,
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required
                        }
                    }
                })
            except Exception as e:
                print(f"Error generating definition for {name}: {e}")

        return definitions

    def execute(self, tool_name, tool_context=None, **kwargs):
        """Executes a tool."""
        if tool_name not in self.tools:
            return f"Error: Tool '{tool_name}' not found."

        func = self.tools[tool_name]
        meta = self.tool_metadata.get(tool_name, {})
        requires_context = meta.get("requires_context", False)

        try:
            # Inject context if required or if explicitly requested in signature
            sig = inspect.signature(func)

            # Legacy context handling: some tools use explicit 'bot', 'chat_id' args
            if tool_context:
                if "chat_id" in sig.parameters and "chat_id" in tool_context:
                    kwargs["chat_id"] = tool_context["chat_id"]
                if "bot" in sig.parameters and "bot" in tool_context:
                    kwargs["bot"] = tool_context["bot"]
                if "job_queue" in sig.parameters and "job_queue" in tool_context:
                    kwargs["job_queue"] = tool_context["job_queue"]
                if "registry" in sig.parameters:
                    # Circular dep risk? pass self or minimal interface?
                    # Legacy modules expect registry object with execute method
                    # But registry also had set_global_context etc.
                    # Let's pass 'self' as registry, assuming it has compatible 'execute' method (it does!)
                    kwargs["registry"] = self

                # Context dict injection
                if "context" in sig.parameters:
                    kwargs["context"] = tool_context

            # If tool marked as requires_context (from legacy registry), merge it into kwargs?
            # Or assume explicit args handling above covers it.

            return func(**kwargs)
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"
