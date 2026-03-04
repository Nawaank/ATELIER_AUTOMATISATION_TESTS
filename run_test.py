from flask import Flask
import requests
import time
import json
from datetime import datetime
import statistics

app = Flask(__name__)

URL = "https://api.open-meteo.com/v1/forecast?latitude=48.77&longitude=2.52&current_weather=true"

# ---------------------
# Étape 1 : Contrat
# ---------------------
def test_contract(response):
    """
    Vérifie le contrat de l'API Open-Meteo :
    - status 200
    - Content-Type JSON
    - champs obligatoires présents
    - types des champs
    """
    result = {"status": "PASS", "details": ""}

    if response.headers.get("Content-Type") != "application/json":
        result["status"] = "FAIL"
        result["details"] += "Content-Type not JSON; "

    try:
        data = response.json()
        required_fields = ["latitude", "longitude", "current_weather"]
        for field in required_fields:
            if field not in data:
                result["status"] = "FAIL"
                result["details"] += f"Missing field: {field}; "
        if "current_weather" in data:
            cw = data["current_weather"]
            if not isinstance(cw.get("temperature"), (int, float)):
                result["status"] = "FAIL"
                result["details"] += "temperature type incorrect; "
            if not isinstance(cw.get("windspeed"), (int, float)):
                result["status"] = "FAIL"
                result["details"] += "windspeed type incorrect; "
    except Exception as e:
        result["status"] = "FAIL"
        result["details"] += f"JSON parse error: {e}; "

    return result

# ---------------------
# Étape 2 : Robustesse / QoS
# ---------------------
def request_with_retry(url, retries=1, timeout=3):
    for attempt in range(retries + 1):
        try:
            start = time.time()
            response = requests.get(url, timeout=timeout)
            latency = round((time.time() - start) * 1000, 2)  # ms
            if response.status_code == 429:
                time.sleep(2)
                continue
            if 500 <= response.status_code < 600:
                time.sleep(1)
                continue
            return response, latency
        except requests.exceptions.RequestException:
            if attempt == retries:
                return None, None
            time.sleep(1)

# ---------------------
# Étape 3 : Tests multiples
# ---------------------
def run_all_tests():
    tests = []
    latencies = []

    # Test principal
    resp, lat = request_with_retry(URL)
    if resp:
        contract = test_contract(resp)
        status = "PASS" if contract["status"]=="PASS" else "FAIL"
        details = contract["details"]
    else:
        status = "FAIL"
        details = "Request failed"
    tests.append({"name":"GET current_weather","status":status,"latency_ms":lat,"details":details})
    if lat: latencies.append(lat)

    # Test avec latitude invalide
    resp, lat = request_with_retry("https://api.open-meteo.com/v1/forecast?latitude=abc&longitude=2.52&current_weather=true")
    if resp and resp.status_code==400:
        status = "PASS"
        details = ""
    else:
        status = "FAIL"
        details = f"Expected 400, got {resp.status_code if resp else 'no response'}"
    tests.append({"name":"GET invalid latitude","status":status,"latency_ms":lat,"details":details})
    if lat: latencies.append(lat)

    # Test avec longitude invalide
    resp, lat = request_with_retry("https://api.open-meteo.com/v1/forecast?latitude=48.77&longitude=abc&current_weather=true")
    if resp and resp.status_code==400:
        status = "PASS"
        details = ""
    else:
        status = "FAIL"
        details = f"Expected 400, got {resp.status_code if resp else 'no response'}"
    tests.append({"name":"GET invalid longitude","status":status,"latency_ms":lat,"details":details})
    if lat: latencies.append(lat)

    # QoS / latence et réussite
    total = len(tests)
    failed = len([t for t in tests if t["status"]=="FAIL"])
    lat_avg = round(sum(latencies)/len(latencies),2) if latencies else 0
    lat_p95 = round(sorted(latencies)[int(0.95*len(latencies))-1],2) if latencies else 0
    error_rate = round((failed/total)*100,2) if total>0 else 0

    run_result = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_tests": total,
        "failed_tests": failed,
        "error_rate_percent": error_rate,
        "latency_avg_ms": lat_avg,
        "latency_p95_ms": lat_p95,
        "tests": tests
    }

    with open("results.json","a") as f:
        f.write(json.dumps(run_result)+"\n")

    return run_result

# ---------------------
# Étape 4 : Dashboard
# ---------------------
@app.route("/")
def dashboard():
    last_run = run_all_tests()  # lance tous les tests à chaque visite

    # Lecture des 20 derniers runs pour graphiques
    try:
        with open("results.json","r") as f:
            lines = f.readlines()
            runs = [json.loads(line) for line in lines]
    except:
        runs = []

    timestamps = [r["timestamp"] for r in runs[-20:]]
    lat_avgs = [r.get("latency_avg_ms",0) for r in runs[-20:]]
    error_rates = [r.get("error_rate_percent",0) for r in runs[-20:]]
    successes = [r["total_tests"] - r["failed_tests"] for r in runs[-20:]]
    failures = [r["failed_tests"] for r in runs[-20:]]

    # Tableau du dernier run
    table_rows = ""
    for t in last_run["tests"]:
        table_rows += f"<tr><td>{t['name']}</td><td>{t['status']}</td><td>{t.get('latency_ms') or '-'}</td><td>{t.get('details') or '-'}</td></tr>"
    table_html = f"""
    <table>
        <tr><th>Test Name</th><th>Status</th><th>Latency (ms)</th><th>Details</th></tr>
        {table_rows}
    </table>
    """

    return f"""
    <html>
    <head>
        <title>API Monitoring - Open Meteo</title>
        <style>
            body {{ font-family: Arial; background-color: #f4f4f9; color: #333; text-align: center; }}
            h1 {{ color: #2c3e50; }}
            table {{ border-collapse: collapse; width: 90%; margin: 20px auto; }}
            th, td {{ padding: 6px 10px; text-align: center; font-size: 0.9em; }}
            th {{ background-color: #2c3e50; color: white; }}
            tr:nth-child(even) {{ background-color: #e9ecef; }}
            .charts-container {{ display: flex; justify-content: center; gap: 40px; margin-top: 20px; flex-wrap: wrap; }}
            .chart-box {{ width: 400px; height: 300px; background-color: #fff; border: 1px solid #ccc; padding: 10px; box-sizing: border-box; }}
        </style>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body>
        <h1>API Monitoring - Open Meteo</h1>
        <p>Dernier run: {last_run['timestamp']} | Total: {last_run['total_tests']} | Failed: {last_run['failed_tests']} | Error rate: {last_run['error_rate_percent']}% | Lat Avg: {last_run['latency_avg_ms']} ms | Lat P95: {last_run['latency_p95_ms']} ms</p>

        <div class="charts-container">
            <div class="chart-box">
                <canvas id="latencyChart"></canvas>
            </div>
            <div class="chart-box">
                <canvas id="errorChart"></canvas>
            </div>
            <div class="chart-box">
                <canvas id="pieChart"></canvas>
            </div>
        </div>

        <h2>Détails du dernier run</h2>
        {table_html}

        <script>
            const latencyCtx = document.getElementById('latencyChart').getContext('2d');
            new Chart(latencyCtx, {{
                type: 'line',
                data: {{
                    labels: {timestamps},
                    datasets: [{{
                        label: 'Latence moyenne (ms)',
                        data: {lat_avgs},
                        borderColor: 'rgb(75,192,192)',
                        backgroundColor: 'rgba(75,192,192,0.2)',
                        tension: 0.3
                    }}]
                }},
                options: {{ responsive:true, maintainAspectRatio:false, scales:{{ y:{{ beginAtZero:true }} }} }}
            }});

            const errorCtx = document.getElementById('errorChart').getContext('2d');
            new Chart(errorCtx, {{
                type: 'line',
                data: {{
                    labels: {timestamps},
                    datasets: [{{
                        label: 'Taux d\'erreur (%)',
                        data: {error_rates},
                        borderColor: 'rgb(255,99,132)',
                        backgroundColor: 'rgba(255,99,132,0.2)',
                        tension: 0.3
                    }}]
                }},
                options: {{ responsive:true, maintainAspectRatio:false, scales:{{ y:{{ beginAtZero:true }} }} }}
            }});

            const pieCtx = document.getElementById('pieChart').getContext('2d');
            new Chart(pieCtx, {{
                type: 'pie',
                data: {{
                    labels: ['Success', 'Failed'],
                    datasets: [{{
                        data: [{successes[-1:] + failures[-1:] if successes else [0,0]}],
                        backgroundColor: ['#4CAF50','#FF6384']
                    }}]
                }},
                options: {{ responsive:true, maintainAspectRatio:false, aspectRatio:1 }}
            }});
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    app.run(debug=True)