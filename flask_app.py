from flask import Flask
import requests
import time
import json
from datetime import datetime

app = Flask(__name__)

URL = "https://api.open-meteo.com/v1/forecast?latitude=48.77&longitude=2.52&current_weather=true"

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

    with open("results.json", "a") as f:
        f.write(json.dumps(result) + "\n")
    return result

@app.route("/")
def dashboard():
    test_api()  # exécute un test à chaque visite

    # Lecture des résultats
    try:
        with open("results.json", "r") as f:
            lines = f.readlines()
            data = [json.loads(line) for line in lines]
    except:
        data = []

    total = len(data)
    success = len([d for d in data if d["success"]])
    avg_time = round(
        sum(d["response_time_ms"] for d in data if d["response_time_ms"]) / success,
        2
    ) if success > 0 else 0
    availability = round((success / total) * 100, 2) if total > 0 else 0

    # Tableau des 10 derniers tests
    table_rows = "".join(
        f"<tr><td>{d['timestamp']}</td><td>{d['status_code']}</td><td>{d['response_time_ms'] or '-'}</td></tr>"
        for d in data[-10:]
    )
    table_html = f"<table><tr><th>Timestamp</th><th>Status</th><th>Response Time (ms)</th></tr>{table_rows}</table>"

    # Graphiques des 20 derniers tests
    timestamps = [d['timestamp'] for d in data[-20:]]
    response_times = [d['response_time_ms'] or 0 for d in data[-20:]]

    return f"""
    <html>
    <head>
    <title>API Monitoring - Open Meteo</title>
    <style>
    body {{ font-family: Arial; background-color: #f4f4f9; color: #333; text-align: center; }}
    h1 {{ color: #2c3e50; }}
    table {{ border-collapse: collapse; width: 80%; margin: 20px auto; }}
    th, td {{ padding: 6px 10px; text-align: center; font-size: 0.9em; }}
    th {{ background-color: #2c3e50; color: white; }}
    tr:nth-child(even) {{ background-color: #e9ecef; }}
    .charts-container {{ display: flex; justify-content: center; gap: 20px; margin-top: 20px; flex-wrap: wrap; }}
    canvas {{ background-color: #fff; border: 1px solid #ccc; width: 300px !important; height: 200px !important; }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body>
    <h1>API Monitoring - Open Meteo</h1>
    <p>Total tests: {total} | Success: {success} | Availability: {availability}% | Average response time: {avg_time} ms</p>

    <div class="charts-container">
        <canvas id="chart"></canvas>
        <canvas id="pie"></canvas>
    </div>

    <h2>Derniers tests</h2>
    {table_html}

    <script>
    const ctx = document.getElementById('chart').getContext('2d');
    new Chart(ctx, {{
        type: 'line',
        data: {{
            labels: {timestamps},
            datasets: [{{
                label: 'Response Time (ms)',
                data: {response_times},
                borderColor: 'rgb(75, 192, 192)',
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                tension: 0.3,
                pointRadius: 3
            }}]
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            scales: {{ y: {{ beginAtZero: true }} }}
        }}
    }});

    const pieCtx = document.getElementById('pie').getContext('2d');
    new Chart(pieCtx, {{
        type: 'pie',
        data: {{
            labels: ['Success', 'Failed'],
            datasets: [{{
                data: [{success}, {total - success}],
                backgroundColor: ['#4CAF50', '#FF6384']
            }}]
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false
        }}
    }});
    </script>
    </body>
    </html>
    """