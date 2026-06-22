import os
import time
import random
import sqlite3
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form, Depends
from fastapi.staticfiles import StaticFiles

app = FastAPI()
PORT = 3000
ADMIN_SECRET = "Maison2026"
# Use /tmp/ on Vercel so the database can initialize cleanly without permission crashes
import sys
if "vercel" in sys.modules or os.environ.get("VERCEL"):
    DB_FILE = "/tmp/pastries.db"
else:
    DB_FILE = "pastries.db"
    
if "vercel" in sys.modules or os.environ.get("VERCEL"):
    UPLOAD_DIR = "/tmp/uploads"
else:
    UPLOAD_DIR = os.path.join("public", "uploads")

# Only try to create the directory locally, or use /tmp/ on Vercel
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Database Helper function to get a clean connection connection channel
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # Enables fetching rows as dictionaries
    return conn

# Database Initialization: Create relational tables & apply seeds if empty
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create the SQL table structure
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pastries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price TEXT NOT NULL,
            status TEXT NOT NULL,
            image TEXT NOT NULL
        )
    ''')
    conn.commit()

    # Check if table is empty to apply seed entries
    cursor.execute('SELECT COUNT(*) FROM pastries')
    if cursor.fetchone()[0] == 0:
        seed_data = [
            ("Almond Croissant", "4.75", "Freshly Baked", "https://images.unsplash.com/photo-1555507036-ab1f4038808a?auto=format&fit=crop&w=400&q=80"),
            ("Raspberry Tart", "6.20", "Only 3 Left!", "https://images.unsplash.com/photo-1587314168485-3236d6710814?auto=format&fit=crop&w=400&q=80")
        ]
        cursor.executemany('INSERT INTO pastries (name, price, status, image) VALUES (?, ?, ?, ?)', seed_data)
        conn.commit()
        print("Database initialized and seeded with baseline SQL rows!")
        
    conn.close()

init_db()

# Security gate check dependency
def authorize_admin(x_admin_secret: str = Header(None)):
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Invalid Admin Passcode. Access Denied.")
    return x_admin_secret

# API: Get all pastries
@app.get("/api/pastries")
async def get_pastries():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM pastries')
        rows = cursor.fetchall()
        conn.close()
        
        # Format the SQL results to match your JavaScript expected _id parameter smoothly
        items = []
        for row in rows:
            items.append({
                "_id": str(row["id"]),
                "name": row["name"],
                "price": row["price"],
                "status": row["status"],
                "image": row["image"]
            })
        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# API: Add a new pastry item (Admin with Device Upload capability)
@app.post("/api/pastries", status_code=201)
async def add_pastry(
    name: str = Form(...),
    price: str = Form(...),
    status: str = Form(None),
    imageFile: UploadFile = File(None),
    _Secret: str = Depends(authorize_admin)
):
    try:
        image_location = "https://placehold.co/400x300/f5f5f4/a8a29e?text=No+Photo"
        
        if imageFile:
            file_extension = os.path.splitext(imageFile.filename)[1]
            unique_suffix = f"{int(time.time() * 1000)}-{random.randint(1, 1000000000)}"
            filename = f"{unique_suffix}{file_extension}"
            file_path = os.path.join(UPLOAD_DIR, filename)
            
            with open(file_path, "wb") as buffer:
                content = await imageFile.read()
                buffer.write(content)
                
            image_location = f"/uploads/{filename}"

        item_status = status if status else "Freshly Baked"

        # SQL Insertion execution pipeline
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO pastries (name, price, status, image) VALUES (?, ?, ?, ?)',
            (name, price, item_status, image_location)
        )
        conn.commit()
        new_row_id = cursor.lastrowid
        conn.close()

        return {
            "_id": str(new_row_id),
            "name": name,
            "price": price,
            "status": item_status,
            "image": image_location
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# API: Delete a pastry item (Admin with Local Image cleanup)
@app.delete("/api/pastries/{item_id}")
async def delete_pastry(item_id: str, _Secret: str = Depends(authorize_admin)):
    try:
        if item_id == "test_auth_id":
            return {"success": True, "message": "Authorization valid"}

        if not item_id.isdigit():
            raise HTTPException(status_code=400, detail="Invalid item ID format")

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Grab image references to clean file structure locally
        cursor.execute('SELECT image FROM pastries WHERE id = ?', (int(item_id),))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Item not found")

        image_path = row["image"]
        if image_path and image_path.startswith("/uploads/"):
            # Extract the part after "/uploads/"
            relative_path = image_path[len("/uploads/"):]
            full_path = os.path.join(UPLOAD_DIR, relative_path)
            if os.path.exists(full_path):
                os.remove(full_path)

        # Execute relational deletion command
        cursor.execute('DELETE FROM pastries WHERE id = ?', (int(item_id),))
        conn.commit()
        conn.close()
        
        return {"success": True, "message": "Item removed"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve static assets
print(f"DEBUG: os.path.exists('public') = {os.path.exists('public')}", flush=True)
if os.path.exists("public"):
    print("DEBUG: Mounting static files at '/'", flush=True)
    app.mount("/", StaticFiles(directory="public", html=True), name="public")
else:
    print("DEBUG: public directory not found!", flush=True)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run('server:app', host="0.0.0.0", port=PORT,reload=True)
    app.mount("/", StaticFiles(directory="public", html=True), name="public")