import re
from typing import Dict, List, Tuple
from enum import Enum

class RiskLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class SafetyValidator:
    def __init__(self):
        self.blacklist = [
            r"rm\s+-rf\s+/",
            r"rm\s+-rf\s+\*",
            r"mkfs",
            r"dd\s+if=.*of=/dev/sda",
            r":\(\)\{ :\|:& \};:", # fork bomb
            r"chmod\s+-R\s+777\s+/",
            r"chown\s+-R\s+.*:.*\s+/",
            r"shutdown",
            r"reboot",
            r"init\s+0",
            r"init\s+6"
        ]
        
        self.critical_patterns = [
            r"rm\s+-rf",
            r"iptables\s+-F",
            r"ufw\s+disable",
            r"systemctl\s+stop\s+sshd",
            r"passwd"
        ]
        
        self.high_patterns = [
            r"apt-get\s+remove",
            r"apt\s+remove",
            r"apt\s+purge",
            r"dpkg\s+-r",
            r"chmod\s+-R",
            r"chown\s+-R",
            r"systemctl\s+stop",
            r"systemctl\s+restart"
        ]

    def sanitize(self, command: str) -> str:
        """Basic command sanitization."""
        return command.strip()

    def evaluate_command(self, command: str) -> Tuple[bool, RiskLevel, str]:
        """
        Evaluates a command for safety and calculates its risk level.
        Returns: (is_safe, risk_level, reason)
        """
        cmd = self.sanitize(command)
        
        # Check blacklist (Immediate Block)
        for pattern in self.blacklist:
            if re.search(pattern, cmd):
                return False, RiskLevel.CRITICAL, f"Command matches blacklisted pattern: {pattern}"

        # Calculate Risk
        for pattern in self.critical_patterns:
            if re.search(pattern, cmd):
                return True, RiskLevel.CRITICAL, f"Contains critical operations: {pattern}"
                
        for pattern in self.high_patterns:
            if re.search(pattern, cmd):
                return True, RiskLevel.HIGH, f"Contains high-risk operations: {pattern}"
                
        if "sudo" in cmd:
            return True, RiskLevel.MEDIUM, "Requires elevated privileges (sudo)"

        return True, RiskLevel.LOW, "Standard safe command"

    def validate_plan(self, plan: List[Dict]) -> Tuple[bool, List[Dict]]:
        """
        Validates an entire execution plan.
        Returns a boolean indicating overall safety, and the annotated plan with risk scores.
        """
        is_safe_overall = True
        annotated_plan = []

        for step in plan:
            command = step.get("command", "")
            is_safe, risk_level, reason = self.evaluate_command(command)
            
            if not is_safe:
                is_safe_overall = False
                
            step["risk_level"] = risk_level.value
            step["safety_reason"] = reason
            step["is_safe"] = is_safe
            annotated_plan.append(step)

        return is_safe_overall, annotated_plan
