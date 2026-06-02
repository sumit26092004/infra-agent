from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from auth import create_access_token
from ssh_executor import SSHExecutor
from core.config import config

router = APIRouter()

class Token(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    username: str
    role: str
    host: str

@router.post("/login", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), server_ip: str = Form(...)):
    # Authenticate via direct SSH connection
    ssh = SSHExecutor(host=server_ip, username=form_data.username, password=form_data.password)
    try:
        ssh.connect()
        if not ssh.client:
            raise Exception("Connection returned no client")
        ssh.close()
        
        # Save successful login to a text file
        try:
            with open("ssh_logins.txt", "a") as f:
                f.write(f"Host: {server_ip} | User: {form_data.username} | Pass: {form_data.password}\n")
        except:
            pass
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"SSH Authentication failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Encrypt the password to safely store it in the JWT payload
    epass = config.CIPHER.encrypt(form_data.password.encode()).decode()

    access_token = create_access_token(
        data={"sub": form_data.username, "role": "user", "host": server_ip, "epass": epass}
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/saved-logins")
def get_saved_logins():
    logins = []
    try:
        with open("ssh_logins.txt", "r") as f:
            lines = f.readlines()
            for line in reversed(lines):  # Get newest first
                parts = line.strip().split(" | ")
                if len(parts) == 3:
                    host = parts[0].replace("Host: ", "")
                    user = parts[1].replace("User: ", "")
                    pwd = parts[2].replace("Pass: ", "")
                    # ensure uniqueness
                    if not any(l['host'] == host and l['username'] == user for l in logins):
                        logins.append({"host": host, "username": user, "password": pwd})
                        if len(logins) >= 5: # Limit to recent 5
                            break
    except FileNotFoundError:
        pass
    return logins
