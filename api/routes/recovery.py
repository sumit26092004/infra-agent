from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import sqlite3
import random
import string
import datetime
from database import get_db
from ssh_executor import SSHExecutor
from rich import print

router = APIRouter()

class ForgotPasswordRequest(BaseModel):
    username: str
    host: str
    email: str

class ResetPasswordRequest(BaseModel):
    username: str
    host: str
    email: str
    otp: str

def get_master_ssh(host: str):
    """
    Connects to the target host using the master infra credentials.
    """
    ssh = SSHExecutor(host=host, username="infra", password="Qwertyuiop@197")
    try:
        ssh.connect()
        if ssh.client:
            return ssh
        return None
    except Exception as e:
        print(f"[red]Master SSH Connection Failed: {e}[/red]")
        return None

def check_user_exists(ssh, username: str) -> bool:
    res = ssh.run_command(f"id -u {username}", get_pty=False)
    return res["exit_code"] == 0

def reset_user_password(ssh, username: str, new_password: str) -> bool:
    # Use sudo chpasswd to change password. SSHExecutor handles sudo password automatically if get_pty=True.
    cmd = f"echo '{username}:{new_password}' | sudo chpasswd"
    res = ssh.run_command(cmd, get_pty=True)
    if res["exit_code"] != 0:
        print(f"[red]Failed to reset password: {res['error'] or res['output']}[/red]")
    return res["exit_code"] == 0

@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    client = get_master_ssh(req.host)
    if not client:
        raise HTTPException(status_code=500, detail="Unable to connect to server as administrator.")
    
    try:
        exists = check_user_exists(client, req.username)
        if not exists:
            # We silently return success to avoid user enumeration, or fail.
            # The prompt says: "only if the user is available in the system then only it will insert there mail id insert the otp"
            raise HTTPException(status_code=404, detail="User does not exist on the target server.")
            
        # Generate OTP
        otp = ''.join(random.choices(string.digits, k=6))
        expires_at = datetime.datetime.now() + datetime.timedelta(minutes=10)
        
        # Save OTP to database
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO otps (username, host, email, otp, expires_at) VALUES (?, ?, ?, ?, ?)",
            (req.username, req.host, req.email, otp, expires_at)
        )
        conn.commit()
        conn.close()
        
        # Real Email Delivery via Gmail SMTP
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        sender_email = "sumitrai2609@gmail.com"
        sender_password = "cqeqseiw sdyznwwp".replace(" ", "")  # Clean up spaces if any
        
        try:
            msg = MIMEMultipart()
            msg['From'] = f"InfraAgent <{sender_email}>"
            msg['To'] = req.email
            msg['Subject'] = "InfraAgent SSH Password Reset OTP"
            
            body = f"Hello,\n\nYour OTP for resetting the SSH password for user '{req.username}' on server '{req.host}' is: {otp}\n\nThis OTP is valid for 10 minutes.\n\n- InfraAgent"
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
            server.quit()
            print(f"[bold green]Successfully sent OTP email to {req.email}[/bold green]")
        except Exception as e:
            print(f"[bold red]Failed to send email via SMTP: {e}[/bold red]")
        
        return {"message": "If the user exists, an OTP has been sent to the provided email."}
    finally:
        client.close()


@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest):
    conn = get_db()
    cursor = conn.cursor()
    
    # Check OTP
    cursor.execute("""
        SELECT id, expires_at FROM otps 
        WHERE username = ? AND host = ? AND email = ? AND otp = ? AND used = 0
        ORDER BY id DESC LIMIT 1
    """, (req.username, req.host, req.email, req.otp))
    
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid OTP.")
        
    expires_at_str = row["expires_at"]
    try:
        if "." in expires_at_str:
            expires_at = datetime.datetime.strptime(expires_at_str, "%Y-%m-%d %H:%M:%S.%f")
        else:
            expires_at = datetime.datetime.strptime(expires_at_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        # Fallback if format is completely unexpected
        expires_at = datetime.datetime.now()
        
    if datetime.datetime.now() > expires_at:
        conn.close()
        raise HTTPException(status_code=400, detail="OTP has expired.")
        
    # Mark OTP as used
    cursor.execute("UPDATE otps SET used = 1 WHERE id = ?", (row["id"],))
    conn.commit()
    conn.close()
    
    # Generate new random password
    new_password = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$%^&*", k=12))
    
    client = get_master_ssh(req.host)
    if not client:
        raise HTTPException(status_code=500, detail="Unable to connect to server as administrator to reset password.")
        
    try:
        success = reset_user_password(client, req.username, new_password)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to reset the password on the remote system.")
            
        return {
            "message": "Password successfully reset.",
            "new_password": new_password
        }
    finally:
        client.close()
