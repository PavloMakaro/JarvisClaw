import json
from typing import Dict, Any, List

class DecisionLayer:
    def __init__(self, llm_service):
        self.llm = llm_service

    async def decide(self, user_input: str, history: List[Dict], available_tools: List[Dict]) -> Dict[str, Any]:
        """
        Decides the next action: RESPOND_DIRECTLY, USE_TOOL, or CREATE_PLAN.
        Returns a dict with 'action' and 'details'.
        """

        # Construct a specialized prompt for decision making
        tool_names = [t["function"]["name"] for t in available_tools]

        system_prompt = f"""
You are the Decision Layer of an AI agent.
Analyze the user request and decide the best course of action.

AVAILABLE TOOLS: {', '.join(tool_names)}

DECISION OPTIONS:
1. RESPOND_DIRECTLY: If the user greets, asks a simple question (identity, capabilities), or if you can answer from your knowledge/memory WITHOUT tools.
2. USE_TOOL: If the request requires a SINGLE tool execution (e.g., "what time is it?", "search for X").
3. CREATE_PLAN: If the request implies MULTIPLE steps (e.g., "search for X and then summarize", "create a report").

OUTPUT FORMAT (JSON ONLY):
{{
  "decision": "RESPOND_DIRECTLY" | "USE_TOOL" | "CREATE_PLAN",
  "reasoning": "Short explanation",
  "tool_name": "name_of_tool" (only for USE_TOOL),
  "tool_args": {{ "arg": "value" }} (only for USE_TOOL)
}}

Minimze steps. If you can answer directly, do so.
"""

        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # Add limited history context (last 3 messages)
        messages.extend(history[-3:])
        messages.append({"role": "user", "content": user_input})

        try:
            # Force JSON mode if supported or just ask for JSON
            response = await self.llm.generate(
                messages,
                provider="deepseek", # Use DeepSeek for reasoning
                stream=False
            )

            if isinstance(response, str):
                print(f"Decision failed due to LLM error: {response}")
                return {"decision": "RESPOND_DIRECTLY", "reasoning": f"LLM Error: {response}"}

            content = response.content
            # Clean up markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            decision_data = json.loads(content)
            return decision_data

        except Exception as e:
            # Fallback
            print(f"Decision error: {e}")
            return {"decision": "RESPOND_DIRECTLY", "reasoning": "Error in decision layer"}
