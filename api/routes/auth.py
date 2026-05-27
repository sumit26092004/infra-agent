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
