import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class InfraAgent:

    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1"
        )

    def generate_commands(self, task):

        prompt = f"""
You are a Linux DevOps expert.

Convert the following infrastructure request into Linux shell commands.

Rules:
- Return ONLY a valid JSON array of strings
- No markdown, no backticks, no explanations
- Ubuntu/Debian commands only
- Safe provisioning commands only
- CRITICAL: If your command contains backslashes (like in sed, awk, or regex), you MUST double-escape them for JSON (e.g., use \\\\s instead of \\s).

Example output:
["sudo apt update", "sudo apt install -y nginx"]

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
            return json.loads(output)

        except json.JSONDecodeError:
            print("Invalid AI response:")
            print(output)
            raise