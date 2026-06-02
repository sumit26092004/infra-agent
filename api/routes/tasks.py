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

# Cache SSH connections to avoid reconnecting every 3 seconds for health checks
ssh_sessions = {}

def get_cached_ssh(current_user: dict):
    key = f"{current_user['username']}@{current_user['host']}"
    if key in ssh_sessions:
        ssh = ssh_sessions[key]
        if ssh.client and ssh.client.get_transport() and ssh.client.get_transport().is_active():
            return ssh
    
    # Otherwise connect
    ssh = SSHExecutor(
        host=current_user["host"],
        username=current_user["username"],
        password=current_user["password"]
    )
    ssh.connect()
    if ssh.client:
        ssh_sessions[key] = ssh
    return ssh

class PlanRequest(BaseModel):
    task: str

class ExecuteConfirmedRequest(BaseModel):
    plan: List[Dict[str, Any]]

class AnalyzeLogsRequest(BaseModel):
    logs: str

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

@router.get("/health")
def get_server_health(current_user: dict = Depends(get_current_user)):
    ssh = get_cached_ssh(current_user)
    if not ssh or not ssh.client:
        raise HTTPException(status_code=500, detail="Failed to connect to server for health metrics")
        
    cmd = r"""
    cpu_usage=$(top -bn1 | awk '/Cpu\(s\)/ {for(i=1;i<=NF;i++) if($i=="id" || $i=="id,") print $(i-1)}' | awk '{print 100 - $1}')
    if [ -z "$cpu_usage" ]; then cpu_usage="0"; fi
    
    load_avg=$(uptime | awk -F'load average:' '{print $2}' | sed 's/^ *//')
    
    read ram_total ram_used ram_free <<< $(free -m | awk 'NR==2{print $2,$3,$4}')
    if [ -z "$ram_total" ]; then ram_total=1; ram_used=0; ram_free=0; fi
    ram_percent=$(awk -v t=$ram_total -v u=$ram_used 'BEGIN {if(t>0) printf "%.1f", u*100/t; else print 0}')
    
    read disk_percent disk_avail <<< $(df -h / | awk '$NF=="/"{print $5,$4}' | sed 's/%//')
    if [ -z "$disk_percent" ]; then disk_percent="0"; disk_avail="0G"; fi
    
    net=$(cat /proc/net/dev | grep -v 'lo:' | awk 'NR>2{rx+=$2; tx+=$10} END{print rx, tx}')
    
    services_running_out=$(systemctl list-units --all --type=service --state=running --no-pager --no-legend 2>/dev/null)
    if [ -z "$services_running_out" ]; then
        services_running=0; running_names="";
    else
        services_running=$(echo "$services_running_out" | wc -l);
        running_names=$(echo "$services_running_out" | grep -o '[^ ]*\.service' | tr '\n' ',' | sed 's/,$//');
    fi
    
    services_failed_out=$(systemctl list-units --all --type=service --state=failed --no-pager --no-legend 2>/dev/null)
    if [ -z "$services_failed_out" ]; then 
        num_failed=0; failed_names=""; 
    else 
        num_failed=$(echo "$services_failed_out" | wc -l); 
        failed_names=$(echo "$services_failed_out" | grep -o '[^ ]*\.service' | tr '\n' ',' | sed 's/,$//'); 
    fi
    
    services_inactive_out=$(systemctl list-units --all --type=service --state=inactive --no-pager --no-legend 2>/dev/null)
    if [ -z "$services_inactive_out" ]; then
        services_inactive=0; inactive_names="";
    else
        services_inactive=$(echo "$services_inactive_out" | wc -l);
        inactive_names=$(echo "$services_inactive_out" | grep -o '[^ ]*\.service' | tr '\n' ',' | sed 's/,$//');
    fi
    
    os_info=$(cat /etc/os-release 2>/dev/null | grep '^PRETTY_NAME=' | cut -d '"' -f 2)
    if [ -z "$os_info" ]; then os_info="Unknown OS"; fi
    
    serial=$(cat /sys/class/dmi/id/product_serial 2>/dev/null)
    if [ -z "$serial" ]; then serial="Unknown Serial"; fi
    
    echo "$cpu_usage|$ram_percent|$disk_percent|$net|$load_avg|$ram_total|$ram_free|$disk_avail|$services_running|$num_failed|$failed_names|$running_names|$services_inactive|$inactive_names|$os_info|$serial"
    """
    
    res = ssh.run_command(cmd, get_pty=False)
    if res["exit_code"] != 0:
        return {"cpu": 0, "ram": 0, "disk": 0, "rx": 0, "tx": 0, "load_avg": "N/A", "ram_total": 0, "ram_free": 0, "disk_avail": "N/A"}
        
    try:
        # Without a PTY, the output will not be wrapped or echoed.
        # It should just be the single pipe-delimited string.
        output_lines = [line.strip() for line in res["output"].split('\n') if '|' in line and len(line.split('|')) >= 10]
        if not output_lines:
            raise ValueError(f"No valid metrics found. Raw output: {res['output']}")
            
        parts = output_lines[-1].split("|")
        cpu = round(float(parts[0]), 1)
        ram = round(float(parts[1]), 1)
        disk = int(parts[2])
        net_parts = parts[3].split()
        rx = int(net_parts[0]) if len(net_parts) > 0 else 0
        tx = int(net_parts[1]) if len(net_parts) > 1 else 0
        
        load_avg = parts[4] if len(parts) > 4 else "N/A"
        ram_total = int(parts[5]) if len(parts) > 5 else 0
        ram_free = int(parts[6]) if len(parts) > 6 else 0
        disk_avail = parts[7] if len(parts) > 7 else "N/A"
        
        services_running = int(parts[8]) if len(parts) > 8 else 0
        services_failed = int(parts[9]) if len(parts) > 9 else 0
        failed_names = parts[10] if len(parts) > 10 else ""
        running_names = parts[11] if len(parts) > 11 else ""
        services_inactive = int(parts[12]) if len(parts) > 12 else 0
        inactive_names = parts[13] if len(parts) > 13 else ""
        os_info = parts[14] if len(parts) > 14 else ""
        serial = parts[15] if len(parts) > 15 else ""
        
        return {
            "cpu": cpu,
            "ram": ram,
            "disk": disk,
            "rx": rx,
            "tx": tx,
            "load_avg": load_avg,
            "ram_total": ram_total,
            "ram_free": ram_free,
            "disk_avail": disk_avail,
            "services_running": services_running,
            "services_failed": services_failed,
            "failed_names": failed_names,
            "running_names": running_names,
            "services_inactive": services_inactive,
            "inactive_names": inactive_names,
            "os_info": os_info,
            "serial": serial
        }
    except Exception as e:
        print(f"Error parsing health metrics: {e}")
        return {"cpu": 0, "ram": 0, "disk": 0, "rx": 0, "tx": 0, "load_avg": "N/A", "ram_total": 0, "ram_free": 0, "disk_avail": "N/A"}

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

from llm_service import llm_service

@router.post("/analyze-logs")
def analyze_logs_endpoint(req: AnalyzeLogsRequest, current_user: dict = Depends(get_current_user)):
    try:
        diagnosis = llm_service.analyze_logs(req.logs)
        return {"diagnosis": diagnosis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi import WebSocket, WebSocketDisconnect
import paramiko
import asyncio

@router.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket, token: str):
    await websocket.accept()
    
    try:
        # Decode token to get credentials
        payload = decode_access_token(token)
        if payload is None:
            await websocket.close(code=1008)
            return
            
        username = payload.get("sub")
        host = payload.get("host")
        epass = payload.get("epass")
        password = config.CIPHER.decrypt(epass.encode()).decode()
        
        # Open SSH Connection
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=host, username=username, password=password, timeout=10)
        
        # Open Interactive Shell
        channel = ssh.invoke_shell(term='xterm', width=100, height=30)
        
        async def read_from_ws():
            try:
                while True:
                    data = await websocket.receive_text()
                    channel.send(data)
            except WebSocketDisconnect:
                pass
            except Exception as e:
                print(f"WS Read error: {e}")

        async def read_from_ssh():
            try:
                while not channel.exit_status_ready():
                    if channel.recv_ready():
                        data = channel.recv(1024).decode('utf-8', errors='ignore')
                        await websocket.send_text(data)
                    else:
                        await asyncio.sleep(0.01)
            except Exception as e:
                print(f"SSH Read error: {e}")
                
        ws_task = asyncio.create_task(read_from_ws())
        ssh_task = asyncio.create_task(read_from_ssh())
        
        done, pending = await asyncio.wait([ws_task, ssh_task], return_when=asyncio.FIRST_COMPLETED)
        
        for task in pending:
            task.cancel()
            
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        if 'channel' in locals():
            channel.close()
        if 'ssh' in locals():
            ssh.close()
        try:
            await websocket.close()
        except:
            pass
