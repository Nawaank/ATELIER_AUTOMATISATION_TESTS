from flask import Flask
import requests
import time
import json
from datetime import datetime
import os

app = Flask(__name__)

URL = "https://api.open-meteo.com/v1/forecast?latitude=48.77&longitude=2.52&current_weather=true"
RESULT_FILE = "results.json"

# S'assure que le fichier results.json existe
if not os.path.exists(RESULT_FILE):
    with open(RESULT_FILE, "w") as f:
        f.write("")

def test_api():
    start = time.time()
    
    try:
        response = requests.get(URL, timeout=5)
        response_time = round((time.time() - start) * 1000, 2)
        success = response.status_code == 200

        result = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status_code": response.status_code,
            "response_time_ms": response_time,
            "success": success
        }

    except:
        result = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status_code": "ERROR",
            "response_time_ms": None,
            "success": False
        }

    try:
        with open(RESULT_FILE, "a") as f:
            f.write(json.dumps(result) + "\n")
    except:
        pass

    return result

@app.route("/")
def dashboard():
    # Test API à chaque visite
    test_api()

    try:
        with open(RESULT_FILE, "r") as f:
            lines = f.readlines()
            data = [json.loads(line) for line in lines if line.strip()]
    except:
        data = []

    total = len(data)
    success = len([d for d in data if d.get("success")])
    avg_time = round(
        sum(d.get("response_time_ms", 0) for d in data if d.get("response_time_ms") is not None) / success,
        2
    ) if success > 0 else 0

    availability = round((success / total) * 100, 2) if total > 0 else 0

    return f"""
    <h1>API Monitoring - Open Meteo</h1>
    <p>Total tests: {total}</p>
    <p>Success: {success}</p>
    <p>Availability: {availability}%</p>
    <p>Average response time: {avg_time} ms</p>
    """