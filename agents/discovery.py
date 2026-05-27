import json
import os
import re
from typing import Dict, Any, List
from openai import OpenAI
from ssh_executor import SSHExecutor
from dotenv import load_dotenv

load_dotenv()

class DiscoveryEngine:
    def __init__(self, ssh: SSHExecutor):
        self.ssh = ssh
        self.client = OpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1"
        )

    def extract_keywords(self, task: str) -> List[str]:
        """Use LLM to extract software/service keywords from the user task for targeted discovery."""
        prompt = f"""
Extract up to 3 core software or service names from this infrastructure task.
Task: {task}
Return ONLY a comma-separated list of lowercase keywords. Example: docker,nginx,kubernetes
"""
        try:
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            keywords = response.choices[0].message.content.strip().lower()
            return [k.strip() for k in keywords.split(",") if k.strip()]
        except Exception:
            return []

    def run_discovery(self, task: str) -> Dict[str, Any]:
        """Runs read-only reconnaissance commands to build a context payload."""
        context = {}
        
        def truncate(text: str, max_lines: int = 15, max_chars: int = 1000) -> str:
            if not text:
                return "None"
            lines = text.splitlines()
            if len(lines) > max_lines:
                lines = lines[:max_lines]
                lines.append("... (truncated)")
            res = "\n".join(lines)
            if len(res) > max_chars:
                return res[:max_chars] + " ... (truncated)"
            return res

        # 1. OS Version
        res_os = self.ssh.run_command("cat /etc/os-release")
        if res_os["exit_code"] == 0:
            context["os_release"] = truncate(res_os["output"], max_lines=10)

        # 2. Open Ports
        res_ports = self.ssh.run_command("ss -tulpn | head -n 10")
        if res_ports["exit_code"] == 0:
            context["open_ports"] = truncate(res_ports["output"], max_lines=10)

        # 3. APT Repositories
        res_repos = self.ssh.run_command("ls -1 /etc/apt/sources.list.d/ || true")
        if res_repos["exit_code"] == 0:
            context["apt_repositories"] = truncate(res_repos["output"], max_lines=10)

        # 4. Targeted Package and Service Discovery
        keywords = self.extract_keywords(task)
        if keywords:
            context["targeted_discovery"] = {}
            for kw in keywords:
                # Sanitize keyword
                if not re.match(r"^[a-z0-9-]+$", kw):
                    continue
                
                pkg_res = self.ssh.run_command(f"dpkg -l | grep -i {kw} | head -n 10 || true")
                svc_res = self.ssh.run_command(f"systemctl is-active {kw} || true")
                
                context["targeted_discovery"][kw] = {
                    "installed_packages": truncate(pkg_res["output"], max_lines=10, max_chars=500),
                    "service_status": truncate(svc_res["output"], max_lines=2, max_chars=100)
                }

        return context
