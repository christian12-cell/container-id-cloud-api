from fastapi import FastAPI, Request
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

# URLs to Box-E API (replace if needed)
BOXE_UPLOAD_URL = "https://box-e.be/API/UploadImage.php"
BOXE_DEMAND_CHECK_URL = "https://box-e.be/API/CheckDemand.php"

# Time between polling checks (in seconds)
CHECK_INTERVAL = 5

# Ensure folder exists
os.makedirs(UPLOAD_DIR, exist_ok=True)

# === Log function ===
def log_event(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[{timestamp}] {message}")

# === Endpoint to receive an image from the Jetson ===
@app.post("/upload")
async def receive_image(request: Request):
    """
    Receives a base64-encoded image from the Jetson and saves it as 'latest.png'
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

# === Simple GET endpoint to check status ===
@app.get("/check")
def status():
    return {
        "status": "running",
        "image_available": os.path.exists(LATEST_FILE)
    }

# === Check if Box-E wants an image ===
def check_demand_from_boxe() -> bool:
    """
    Asks Box-E if it currently needs an image
    """
    try:
        response = requests.get(BOXE_DEMAND_CHECK_URL)
        response.raise_for_status()
        data = response.json()
        return data.get("demand", False)
    except Exception as e:
        log_event(f"Error checking demand from Box-E: {e}")
        return False

# === Loop that checks demand and sends image if needed ===
def polling_loop():
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

# === Start polling loop when API launches ===
@app.on_event("startup")
def start_polling():
    thread = threading.Thread(target=polling_loop, daemon=True)
    thread.start()
