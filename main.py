from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api.routes import auth, tasks, recovery
import os

app = FastAPI(title="Infra Agent Execution Engine")

# Setup static directory
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include Modular Routers
app.include_router(auth.router, tags=["auth"])
app.include_router(tasks.router, tags=["tasks"])
app.include_router(recovery.router, tags=["recovery"])

@app.get("/")
def serve_index():
    return FileResponse("static/index.html")
