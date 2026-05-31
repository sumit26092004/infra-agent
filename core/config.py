import os
import base64
import hashlib
from dotenv import load_dotenv
from cryptography.fernet import Fernet

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=env_path)

class Config:
    # API and Auth
    SECRET_KEY = os.getenv("SECRET_KEY", "super-secure-default-key-change-in-production")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")
    
    # Derived Keys
    FERNET_KEY = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())
    CIPHER = Fernet(FERNET_KEY)

    # Agent Settings
    AI_MODEL = "llama-3.3-70b-versatile"
    
config = Config()
