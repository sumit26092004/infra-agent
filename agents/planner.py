import os
import json
from typing import List, Dict, Any, Tuple
from openai import OpenAI
from dotenv import load_dotenv
from validators.safety import SafetyValidator

load_dotenv()

class ExecutionPlanner:
    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1"
        )
        self.validator = SafetyValidator()

    def generate_plan(self, task: str, system_context: Dict[str, Any] = None) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Takes a natural language task and optional system context, and returns an ordered execution plan.
        Returns: (is_safe_overall, annotated_plan)
        """
        context_str = json.dumps(system_context, indent=2) if system_context else "No context provided."
        
        prompt = f"""
You are a Lead Linux DevOps Engineer and Systems Architect.

Convert the following infrastructure request into a strictly ordered execution plan.

SYSTEM CONTEXT:
{context_str}

Rules:
- Read the SYSTEM CONTEXT above. Do NOT assume the OS version, file paths, or installed packages. Use the provided context to write conditionally accurate commands.
- Return ONLY a valid JSON array of objects.
- No markdown, no backticks, no explanations.
- Ubuntu/Debian commands only.
- Safe provisioning commands only.
- Include pre-execution validation checks in your plan (e.g., check internet, check if package exists before installing).
- CRITICAL: If your command contains backslashes (like in sed, awk, or regex), you MUST double-escape them for JSON (e.g., use \\\\s instead of \\s).

JSON Object Format:
{{
    "step": <integer>,
    "command": "<linux shell command>",
    "purpose": "<brief explanation of what this command does and why it's needed>"
}}

Task:
{task}
"""

        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,
        )

        output = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        if "```" in output:
            output = output.split("```")[1]
            if output.startswith("json"):
                output = output[4:]
            output = output.strip()

        try:
            raw_plan = json.loads(output)
            if not isinstance(raw_plan, list):
                raise ValueError("Expected a JSON array of objects")
                
            # Validate safety and add risk scores
            is_safe_overall, annotated_plan = self.validator.validate_plan(raw_plan)
            return is_safe_overall, annotated_plan

        except json.JSONDecodeError as e:
            print("Invalid AI response (JSON decode error):")
            print(output)
            raise ValueError(f"AI returned invalid JSON: {str(e)}")
        except Exception as e:
            print("Failed to generate plan:")
            print(str(e))
            raise
