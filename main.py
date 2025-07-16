from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse
import base64
import os
from datetime import datetime
import requests
import threading
import time

# === Create FastAPI app ===
app = FastAPI()

# === Configuration ===
UPLOAD_DIR = "latest"                       # Directory to store the latest uploaded image
LOG_FILE = "logs.txt"                       # File to store logs of all events
LATEST_FILE = os.path.join(UPLOAD_DIR, "latest.png")  # Full path to the most recent image

# This is the URL where the image should be sent when Box-E asks for it.
# Replace this with the actual endpoint provided by Box-E when available.
BOXE_UPLOAD_URL = "https://box-e.be/API/UploadImage.php"

# Polling interval (how often to check if Box-E wants an image)
CHECK_INTERVAL = 1  # seconds

# === Global variable to track Box-E demand ===
boxe_wants_image = False  # Set to True when Box-E requests an image

# === Ensure the image upload directory exists ===
os.makedirs(UPLOAD_DIR, exist_ok=True)

# === Logging helper function ===
def log_event(message: str):
    """
    Write a timestamped message to the logs.txt file and print it to console.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[{timestamp}] {message}")

# === Endpoint to receive a base64 image from Jetson device ===
@app.post("/upload")
async def receive_image(request: Request):
    """
    Receives a JSON object from Jetson containing a base64-encoded image.
    The image is saved locally as 'latest/latest.png'.
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
        log_event(f"Error during upload: {e}")
        return {"status": "error", "message": str(e)}

# === Simple API health check endpoint ===
@app.get("/check")
def status():
    """
    Returns API status and whether a latest image exists.
    """
    return {
        "status": "running",
        "image_available": os.path.exists(LATEST_FILE)
    }

# === Endpoint to return the latest image encoded in base64 ===
@app.get("/get-latest-image")
def get_latest_image():
    """
    Returns the latest saved image as a base64-encoded string.
    """
    if not os.path.exists(LATEST_FILE):
        return JSONResponse(status_code=404, content={"status": "error", "message": "No image available"})

    with open(LATEST_FILE, "rb") as f:
        encoded = base64.b64encode(f.read())

    return {
        "status": "ok",
        "filename": "latest.png",
        "image_base64": encoded
    }

# === Endpoint to view the image directly in browser ===
@app.get("/view-image")
def view_image():
    """
    Serves the latest image file for direct viewing in the browser.
    """
    if os.path.exists(LATEST_FILE):
        return FileResponse(LATEST_FILE, media_type="image/png")
    return JSONResponse(status_code=404, content={"status": "error", "message": "No image available"})

# === Endpoint to view logs (debugging / monitoring) ===
@app.get("/view-logs")
def view_logs():
    """
    Displays the contents of the logs.txt file.
    """
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            content = f.read()
        return PlainTextResponse(content)
    return PlainTextResponse("No logs available.")

# === Endpoint to receive demand (true/false) from Box-E ===
@app.post("/receive-demand")
async def receive_demand(request: Request):
    """
    Receives a command from Box-E indicating whether it wants an image.
    Example payload: { "demand": true } or { "demand": false }
    """
    global boxe_wants_image
    try:
        data = await request.json()
        boxe_wants_image = data.get("demand", False)
        log_event(f"Box-E demand received: {'YES' if boxe_wants_image else 'NO'}")
        imgResult = get_latest_image()
        return {"imgResult": imgResult}
    except Exception as e:
        log_event(f"Error in /receive-demand: {e}")
        return {"status": "error", "message": str(e)}

# === Helper function to get current demand state ===
def check_demand_from_boxe() -> bool:
    """
    Returns the current value of boxe_wants_image.
    True if Box-E wants an image.
    """
    global boxe_wants_image
    return boxe_wants_image

# === Polling loop running in background ===
def polling_loop():
    """
    Polling loop that runs in a separate thread.
    If Box-E has requested an image, it sends the latest image to BOXE_UPLOAD_URL.
    """
    log_event("Polling loop started.")
    while True:
       if check_demand_from_boxe()==False:
            log_event("Box-E is not requesting an image.")
        time.sleep(CHECK_INTERVAL)
        
# === Start polling loop on FastAPI startup ===
@app.on_event("startup")
def start_polling():
    """
    Launches the polling thread automatically when the API starts.
    """
    thread = threading.Thread(target=polling_loop, daemon=True)
    thread.start()
