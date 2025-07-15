from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
import base64
import os
from datetime import datetime
import requests
import threading
import time

# Create FastAPI app
app = FastAPI()

# === Configuration ===
UPLOAD_DIR = "latest"  # Folder to store the last image
LOG_FILE = "logs.txt"  # Log file
LATEST_FILE = os.path.join(UPLOAD_DIR, "latest.png")  # Path to saved image

# URLs to Box-E API
BOXE_UPLOAD_URL = "https://box-e.be/API/UploadImage.php"
BOXE_DEMAND_CHECK_URL = "https://box-e.be/API/CheckDemand.php"

# Polling delay in seconds
CHECK_INTERVAL = 5

# Ensure upload folder exists
os.makedirs(UPLOAD_DIR, exist_ok=True)

# === Logging helper ===
def log_event(message: str):
    """Logs a message to a file and prints it with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[{timestamp}] {message}")

# === Endpoint to receive image from Jetson ===
@app.post("/upload")
async def receive_image(request: Request):
    """
    Receives a base64-encoded image from the Jetson and saves it.
    """
    try:
        data = await request.json()
        image_b64 = data["image"]
        filename = data.get("filename", "latest.png")
        image_bytes = base64.b64decode(image_b64)
        with open(LATEST_FILE, "wb") as f:
            f.write(image_bytes)
        log_event(f"Image received: {filename}")
        return {"status": "ok", "message": "Image successfully received"}
    except Exception as e:
        log_event(f"Upload error: {e}")
        return {"status": "error", "message": str(e)}

# === Endpoint to check API status ===
@app.get("/check")
def status():
    """Returns a status indicator and image availability."""
    return {
        "status": "running",
        "image_available": os.path.exists(LATEST_FILE)
    }

# === Endpoint to fetch latest image in base64 ===
@app.get("/get-latest-image")
def get_latest_image():
    """
    Returns the latest image encoded in base64 format.
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

# === NEW: Endpoint to view the latest image directly ===
@app.get("/view-image")
def view_image():
    """
    Returns the latest image as a raw PNG file for direct viewing.
    """
    if os.path.exists(LATEST_FILE):
        return FileResponse(LATEST_FILE, media_type="image/png")
    return JSONResponse(status_code=404, content={"status": "error", "message": "No image available"})

# === Check if Box-E wants an image ===
def check_demand_from_boxe() -> bool:
    """Returns True if Box-E wants an image."""
    try:
        response = requests.get(BOXE_DEMAND_CHECK_URL)
        response.raise_for_status()
        data = response.json()
        return data.get("demand", False)
    except Exception as e:
        log_event(f"Error checking demand from Box-E: {e}")
        return False

# === Polling loop to send image when requested ===
def polling_loop():
    """Continuously polls Box-E and sends the image if needed."""
    log_event("Started polling loop to check Box-E.")
    while True:
        if check_demand_from_boxe():
            log_event("Box-E requested an image.")
            if os.path.exists(LATEST_FILE):
                with open(LATEST_FILE, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode("utf-8")
                payload = {
                    "image": image_data,
                    "filename": "latest.png"
                }
                try:
                    response = requests.post(BOXE_UPLOAD_URL, json=payload)
                    response.raise_for_status()
                    log_event("Image successfully sent to Box-E.")
                except Exception as e:
                    log_event(f"Error sending image to Box-E: {e}")
            else:
                log_event("No image found to send.")
        else:
            log_event("Box-E did not request an image.")
        time.sleep(CHECK_INTERVAL)

# === Start polling on startup ===
@app.on_event("startup")
def start_polling():
    """Starts background polling thread on API startup."""
    thread = threading.Thread(target=polling_loop, daemon=True)
    thread.start()
