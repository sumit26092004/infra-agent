import os
import base64
import hashlib
from dotenv import load_dotenv
from cryptography.fernet import Fernet

load_dotenv()

class Config:
    # API and Auth
    SECRET_KEY = os.getenv("SECRET_KEY", "super-secure-default-key-change-in-production")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    
    # Derived Keys
    FERNET_KEY = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())
    CIPHER = Fernet(FERNET_KEY)

    # Agent Settings
    AI_MODEL = "llama-3.3-70b-versatile"
    
config = Config()
