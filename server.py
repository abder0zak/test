import os
import sys
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# 1. HANDLE DIRECTORIES SAFE FOR VERCEL
# Vercel's runtime environment is read-only except for /tmp
if "vercel" in sys.modules or os.environ.get("VERCEL"):
    UPLOAD_DIR = "/tmp/uploads"
    DB_FILE = "/tmp/pastries.db"
else:
    UPLOAD_DIR = os.path.join("public", "uploads")
    DB_FILE = "pastries.db"

os.makedirs(UPLOAD_DIR, exist_ok=True)

# 2. YOUR API ENDPOINTS GO HERE (Example placeholder)
@app.get("/api/pastries")
def get_pastries():
    return {"message": "Database is connected!", "file": DB_FILE}


# 3. EXPLICIT FRONTEND ROUTING (Fixes the 404 Error)
# This forces the Python server to read your HTML pages directly from disk

@app.get("/")
def read_index():
    index_path = os.path.join("public", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "index.html not found in public folder"}

@app.get("/admin.html")
def read_admin():
    admin_path = os.path.join("public", "admin.html")
    if os.path.exists(admin_path):
        return FileResponse(admin_path)
    return {"error": "admin.html not found in public folder"}


# 4. STATIC CSS/JS ASSETS
# Mount the rest of the public folder so images/styles load properly
if os.path.exists("public"):
 app.mount("/", StaticFiles(directory="public"), name="public")


# 5. LOCAL RUNNER CONFIGURATION
if __name__ == "__main__":
    import uvicorn
    # Hardcoded port example, change to your variable if needed
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)