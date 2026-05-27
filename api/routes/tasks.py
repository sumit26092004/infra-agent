from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from auth import decode_access_token
from fastapi.security import OAuth2PasswordBearer
from ssh_executor import SSHExecutor
from core.config import config
from agents.planner import ExecutionPlanner
from agents.self_healing import SelfHealer
from agents.discovery import DiscoveryEngine

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

class PlanRequest(BaseModel):
    task: str

class ExecuteConfirmedRequest(BaseModel):
    plan: List[Dict[str, Any]]

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
        
    username: str = payload.get("sub")
    host: str = payload.get("host")
    epass: str = payload.get("epass")
    
    if not username or not host or not epass:
        raise credentials_exception
    
    try:
        password = config.CIPHER.decrypt(epass.encode()).decode()
    except Exception:
        raise credentials_exception
    
    return {
        "username": username,
        "host": host,
        "password": password
    }

@router.get("/me")
def read_users_me(current_user: dict = Depends(get_current_user)):
    return {
        "username": current_user["username"],
        "role": "user",
        "host": current_user["host"]
    }

@router.post("/plan")
def plan_task(req: PlanRequest, current_user: dict = Depends(get_current_user)):
    planner = ExecutionPlanner()
    
    # 1. SSH into the server to perform read-only reconnaissance
    ssh = SSHExecutor(
        host=current_user["host"],
        username=current_user["username"],
        password=current_user["password"]
    )
    
    system_context = {}
    try:
        ssh.connect()
        if ssh.client:
            discovery = DiscoveryEngine(ssh)
            system_context = discovery.run_discovery(req.task)
            ssh.close()
    except Exception as e:
        print(f"Discovery failed, proceeding with empty context: {e}")
        if ssh.client:
            ssh.close()
            
    # 2. Generate Context-Aware Execution Plan
    try:
        is_safe, plan = planner.generate_plan(req.task, system_context)
        return {
            "is_safe": is_safe,
            "plan": plan,
            "system_context": system_context
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/execute")
def execute_task(req: ExecuteConfirmedRequest, current_user: dict = Depends(get_current_user)):
    ssh = SSHExecutor(
        host=current_user["host"],
        username=current_user["username"],
        password=current_user["password"]
    )
    
    try:
        ssh.connect()
        if not ssh.client:
            return {"error": "SSH connection failed. Invalid password or host.", "results": []}
        healer = SelfHealer()
        results = []
        
        # Execute each step from the approved plan
        for step in req.plan:
            cmd = step.get("command")
            if not cmd:
                continue
                
            res = ssh.run_command(cmd)
            results.append({"step": step.get("step"), "command": cmd, "result": res})
            
            # Self-healing logic
            if res.get("exit_code") != 0:
                # Trigger self-healer
                fix = healer.generate_fix(cmd, res.get("error"), res.get("output"))
                
                # Append the healer's explanation
                results.append({
                    "step": f"{step.get('step')} (Auto-Fix Attempt)",
                    "command": "AI Self-Healing Engine",
                    "result": {
                        "output": f"Error detected. AI Diagnosis: {fix.get('explanation', 'Unknown')}", 
                        "error": "", 
                        "exit_code": 0
                    }
                })
                
                # Execute fix commands
                fix_failed = False
                for fix_cmd in fix.get("fix_commands", []):
                    fix_res = ssh.run_command(fix_cmd)
                    results.append({"step": f"{step.get('step')} (Fix)", "command": fix_cmd, "result": fix_res})
                    if fix_res.get("exit_code") != 0:
                        fix_failed = True
                        break
                        
                if fix_failed:
                    # Fix failed, abort completely
                    break
                else:
                    # Fix succeeded, retry original command
                    retry_res = ssh.run_command(cmd)
                    results.append({"step": f"{step.get('step')} (Retry)", "command": cmd, "result": retry_res})
                    if retry_res.get("exit_code") != 0:
                        break  # Retry failed, abort
                
        ssh.close()
        return {"results": results}
    except Exception as e:
        if ssh.client:
            ssh.close()
        return {"error": str(e), "results": []}
