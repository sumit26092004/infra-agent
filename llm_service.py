import os
import json
import urllib.request
from core.config import config

class LLMService:
    def __init__(self):
        # We will use urllib directly to bypass any OpenAI SDK timeout quirks
        pass

    def analyze_logs(self, logs: str) -> dict:
        prompt = f"""
You are a Senior Linux SRE and DevOps Engineer.

Analyze infrastructure logs and errors.

Return:
* Root Cause
* Severity (LOW/MEDIUM/HIGH/CRITICAL)
* Recommended Fix
* Safe Linux Commands

Never recommend destructive commands such as:
rm -rf /
mkfs
shutdown
reboot
database deletion

Output must be valid JSON only.

JSON Format Requirements:
{{
  "root_cause": "...",
  "severity": "...",
  "recommended_fix": "...",
  "commands": ["..."]
}}

Logs to analyze:
{logs}
"""
        try:
            url = f"{config.OLLAMA_BASE_URL.replace('/v1', '')}/api/generate"
            payload = {
                "model": config.OLLAMA_MODEL,
                "prompt": prompt.strip(),
                "stream": False,
                "options": {
                    "temperature": 0.0
                }
            }
            
            req = urllib.request.Request(
                url, 
                data=json.dumps(payload).encode('utf-8'), 
                headers={'Content-Type': 'application/json'}
            )
            
            # Set a massive 1-hour timeout (3600 seconds) for slow CPUs
            with urllib.request.urlopen(req, timeout=3600) as response:
                result_data = json.loads(response.read().decode('utf-8'))
                output = result_data.get("response", "").strip()

            import re
            
            # Handle potential <think> tags from deepseek
            if "</think>" in output:
                output = output.split("</think>")[-1].strip()

            # Extract just the JSON object part to ignore any conversational text
            json_match = re.search(r'\{.*\}', output, re.DOTALL)
            if json_match:
                output = json_match.group(0)

            parsed_json = json.loads(output)

            # Normalize data in case small models deviate from the strict schema
            rec_fix = parsed_json.get("recommended_fix", "")
            if isinstance(rec_fix, list):
                parsed_json["recommended_fix"] = " ".join([str(x.get("fix", x.get("step", x))) if isinstance(x, dict) else str(x) for x in rec_fix])
            elif isinstance(rec_fix, dict):
                parsed_json["recommended_fix"] = json.dumps(rec_fix)
            elif not isinstance(rec_fix, str):
                parsed_json["recommended_fix"] = str(rec_fix)

            raw_commands = parsed_json.get("commands", [])
            if isinstance(raw_commands, str):
                raw_commands = [raw_commands]
            
            normalized_commands = []
            for cmd in raw_commands:
                if isinstance(cmd, dict):
                    # Extract the string if the model returned an object like {"command": "..."}
                    val = cmd.get("command", cmd.get("cmd", cmd.get("step", json.dumps(cmd))))
                    normalized_commands.append(str(val))
                elif isinstance(cmd, list):
                    normalized_commands.extend([str(c) for c in cmd])
                else:
                    normalized_commands.append(str(cmd))
            
            parsed_json["commands"] = normalized_commands

            return parsed_json

        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON response: {e}\nRaw output: {output}")
            return {
                "root_cause": "Failed to parse LLM response. The model may have produced malformed JSON.",
                "severity": "CRITICAL",
                "recommended_fix": "Check the LLM response format or use a different model.",
                "commands": []
            }
        except Exception as e:
            print(f"Ollama connection error or timeout: {e}")
            return {
                "root_cause": f"Ollama connection error: {e}",
                "severity": "CRITICAL",
                "recommended_fix": f"Ensure Ollama is running locally and the {config.OLLAMA_MODEL} model is pulled.",
                "commands": []
            }

llm_service = LLMService()
