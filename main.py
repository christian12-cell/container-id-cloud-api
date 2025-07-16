from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse
import base64
import os
from datetime import datetime

# === Create FastAPI app ===
app = FastAPI()

# === Configuration ===
UPLOAD_DIR = "latest"
LOG_FILE = "logs.txt"
LATEST_FILE = os.path.join(UPLOAD_DIR, "latest.png")

# Create the upload folder if it doesn't exist
os.makedirs(UPLOAD_DIR, exist_ok=True)

# === Logging helper ===
def log_event(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[{timestamp}] {message}")

# === Endpoint: receive image from Jetson ===
@app.post("/upload")
async def receive_image(request: Request):
    """
    Receives a base64-encoded image from Jetson.
    Saves it as latest/latest.png
    """
    try:
        data = await request.json()
        image_b64 = data["image"]
        filename = data.get("filename", "latest.png")
        image_bytes = base64.b64decode(image_b64)
        with open(LATEST_FILE, "wb") as f:
            f.write(image_bytes)
        log_event(f"Image received and saved: {filename}")
        return {"status": "ok", "message": "Image successfully received"}
    except Exception as e:
        log_event(f"Upload error: {e}")
        return {"status": "error", "message": str(e)}

# === Endpoint: health check ===
@app.get("/check")
def status():
    """
    Returns API status and image availability.
    """
    return {
        "status": "running",
        "image_available": os.path.exists(LATEST_FILE)
    }

# === Endpoint: return latest image (base64) ===
@app.get("/get-latest-image")
def get_latest_image():
    """
    Returns the latest image as a base64 string.
    """
    if not os.path.exists(LATEST_FILE):
        return JSONResponse(status_code=404, content={"status": "error", "message": "No image available"})

    with open(LATEST_FILE, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    return {
        "status": "ok",
        "filename": "latest.png",
        "image_base64": encoded
    }

# === Endpoint: view latest image (PNG) ===
@app.get("/view-image")
def view_image():
    """
    Returns the latest image as a raw PNG for browser viewing.
    """
    if os.path.exists(LATEST_FILE):
        return FileResponse(LATEST_FILE, media_type="image/png")
    return JSONResponse(status_code=404, content={"status": "error", "message": "No image available"})

# === Endpoint: view logs ===
@app.get("/view-logs")
def view_logs():
    """
    Displays contents of logs.txt for monitoring.
    """
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            return PlainTextResponse(f.read())
    return PlainTextResponse("No logs available.")

# === Endpoint: Box-E requests image ===
@app.post("/receive-demand")
async def receive_demand(request: Request):
    """
    Receives a request from Box-E.
    If demand is true, returns the latest image in base64.
    """
    try:
        data = await request.json()
        demand = data.get("demand", False)
        log_event(f"Box-E demand received: {'YES' if demand else 'NO'}")
        if demand:
            return get_latest_image()
        return {"status": "ok", "message": "Demand is false, no image sent"}
    except Exception as e:
        log_event(f"Error in /receive-demand: {e}")
        return {"status": "error", "message": str(e)}
