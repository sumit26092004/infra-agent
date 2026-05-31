import os
import json
from typing import Dict, Any
from openai import OpenAI
from core.config import config

class SelfHealer:
    def __init__(self):
        self.client = OpenAI(
            api_key=config.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )

    def generate_fix(self, failed_command: str, stderr: str, stdout: str) -> Dict[str, Any]:
        """
        Analyzes a failed command and generates a fix plan.
        """
        prompt = f"""
You are a Linux DevOps Troubleshooting Expert.

A command execution failed. Analyze the error and provide a fix.

Failed Command: {failed_command}
Standard Error: {stderr}
Standard Output: {stdout}

Rules:
- Return ONLY a valid JSON object.
- No markdown, no backticks, no explanations outside the JSON.
- If backslashes are needed in commands, double-escape them.

JSON Object Format:
{{
    "explanation": "<brief explanation of what went wrong>",
    "fix_commands": ["<linux shell command 1>", "<linux shell command 2>"]
}}
"""
        try:
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

            if "```" in output:
                output = output.split("```")[1]
                if output.startswith("json"):
                    output = output[4:]
                output = output.strip()

            return json.loads(output)
            
        except Exception as e:
            print(f"Self-Healer failed to generate fix: {e}")
            return {
                "explanation": "Self-healing agent failed to analyze the error.",
                "fix_commands": []
            }
