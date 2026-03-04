import requests
import time
import json
from datetime import datetime

URL = "https://api.open-meteo.com/v1/forecast?latitude=48.77&longitude=2.52&current_weather=true"

def test_api():
    start = time.time()
    
    try:
        response = requests.get(URL, timeout=5)
        response_time = round((time.time() - start) * 1000, 2)
        
        success = response.status_code == 200
        
        data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status_code": response.status_code,
            "response_time_ms": response_time,
            "success": success
        }
        
    except Exception as e:
        data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status_code": "ERROR",
            "response_time_ms": None,
            "success": False
        }

    return data

result = test_api()

with open("results.json", "a") as f:
    f.write(json.dumps(result) + "\n")