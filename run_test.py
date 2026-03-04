from flask import Flask, redirect
import requests
import time
import json
from datetime import datetime
import storage  # ton fichier storage.py

app = Flask(__name__)

# URL "valide" (cohérente avec ce que tu testes dans le navigateur)
URL = "https://api.open-meteo.com/v1/forecast?latitude=48.77&longitude=2.52&current_weather=true&timezone=Europe/Paris"

# Initialisation DB
storage.init_db()


# ---------------------
# Étape 1 : Contrat
# ---------------------
def test_contract(response):
    result = {"status": "PASS", "details": ""}

    content_type = response.headers.get("Content-Type", "")
    # Accept JSON + charset
    if not content_type.startswith("application/json"):
        result["status"] = "FAIL"
        result["details"] += f"Content-Type not JSON ({content_type}); "

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
    """
    1 retry max
    - timeout
    - 429 -> petite attente
    - 5xx -> retry
    """
    for attempt in range(retries + 1):
        try:
            start = time.time()
            response = requests.get(url, timeout=timeout)
            latency = round((time.time() - start) * 1000, 2)

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

    return None, None


# ---------------------
# Étape 3 : Exécution des tests
# ---------------------
def run_all_tests():
    tests = []
    latencies = []

    # --- Test principal (contrat)
    resp, lat = request_with_retry(URL)
    if resp is not None:
        contract = test_contract(resp)
        status = "PASS" if contract["status"] == "PASS" else "FAIL"
        details = contract["details"] or "-"
    else:
        status = "FAIL"
        details = "Request failed (timeout/retry)"

    tests.append({
        "name": "GET current_weather",
        "status": status,
        "latency_ms": lat,
        "details": details
    })
    if lat is not None:
        latencies.append(lat)

    # --- Test latitude invalide (contrat d'erreur)
    # NOTE: abc peut parfois timeout selon infra; on gère ça => FAIL si pas de réponse
    invalid_lat_url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=abc&longitude=2.52&current_weather=true&timezone=Europe/Paris"
    )
    resp, lat = request_with_retry(invalid_lat_url)

    if resp is None:
        status = "FAIL"
        details = "No response (timeout/retry) -> cannot validate expected error"
    else:
        try:
            data = resp.json()
        except Exception:
            data = {}

        # Contrat attendu : erreur (status >= 400) et/ou JSON error/reason
        if resp.status_code >= 400 or data.get("error") is True or ("reason" in data):
            status = "PASS"
            details = f"Expected error: status_code={resp.status_code}"
            if "reason" in data:
                details += f" | reason={data.get('reason')}"
        else:
            status = "FAIL"
            details = f"Unexpected success: status_code={resp.status_code}"

    tests.append({
        "name": "GET invalid latitude",
        "status": status,
        "latency_ms": lat,
        "details": details
    })
    if lat is not None:
        latencies.append(lat)

    # --- Test longitude invalide (contrat d'erreur)
    invalid_lon_url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=48.77&longitude=abc&current_weather=true&timezone=Europe/Paris"
    )
    resp, lat = request_with_retry(invalid_lon_url)

    if resp is None:
        status = "FAIL"
        details = "No response (timeout/retry) -> cannot validate expected error"
    else:
        try:
            data = resp.json()
        except Exception:
            data = {}

        if resp.status_code >= 400 or data.get("error") is True or ("reason" in data):
            status = "PASS"
            details = f"Expected error: status_code={resp.status_code}"
            if "reason" in data:
                details += f" | reason={data.get('reason')}"
        else:
            status = "FAIL"
            details = f"Unexpected success: status_code={resp.status_code}"

    tests.append({
        "name": "GET invalid longitude",
        "status": status,
        "latency_ms": lat,
        "details": details
    })
    if lat is not None:
        latencies.append(lat)

    # --- QoS
    total = len(tests)
    failed = len([t for t in tests if t["status"] == "FAIL"])

    lat_avg = round(sum(latencies) / len(latencies), 2) if latencies else 0

    # p95 robuste
    if latencies:
        s = sorted(latencies)
        idx = max(0, min(len(s) - 1, int(round(0.95 * len(s))) - 1))
        lat_p95 = round(s[idx], 2)
    else:
        lat_p95 = 0

    error_rate_percent = round((failed / total) * 100, 2) if total > 0 else 0

    run_result = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_tests": total,
        "failed_tests": failed,
        "error_rate_percent": error_rate_percent,
        "latency_avg_ms": lat_avg,
        "latency_p95_ms": lat_p95,
        "tests": tests
    }

    storage.save_run(run_result)
    return run_result


# ---------------------
# Étape 4 : Dashboard
# ---------------------
@app.route("/")
def dashboard():
    last_run = storage.get_last_run()
    runs = storage.list_runs(limit=20)

    # ancien -> récent
    runs = list(reversed(runs))

    timestamps = [r["timestamp"] for r in runs]
    lat_avgs = [r.get("latency_avg_ms", 0) for r in runs]
    error_rates = [r.get("error_rate_percent", 0) for r in runs]

    # pie = dernier run
    if runs:
        last_success = runs[-1]["total_tests"] - runs[-1]["failed_tests"]
        last_fail = runs[-1]["failed_tests"]
    else:
        last_success = 0
        last_fail = 0

    # JSON safe pour injection JS
    timestamps_js = json.dumps(timestamps)
    lat_avgs_js = json.dumps(lat_avgs)
    error_rates_js = json.dumps(error_rates)

    # Tableau du dernier run
    table_rows = ""
    for t in last_run["tests"]:
        table_rows += (
            f"<tr>"
            f"<td>{t['name']}</td>"
            f"<td>{t['status']}</td>"
            f"<td>{t.get('latency_ms') if t.get('latency_ms') is not None else '-'}</td>"
            f"<td>{t.get('details') or '-'}</td>"
            f"</tr>"
        )

    table_html = f"""
    <table>
        <tr><th>Test Name</th><th>Status</th><th>Latency (ms)</th><th>Details</th></tr>
        {table_rows}
    </table>
    """

    # Historique (20 derniers runs)
    history_rows = ""
    for r in runs:
        history_rows += (
            "<tr>"
            f"<td>{r['timestamp']}</td>"
            f"<td>{r['total_tests']}</td>"
            f"<td>{r['failed_tests']}</td>"
            f"<td>{r['error_rate_percent']}%</td>"
            f"<td>{r['latency_avg_ms']}</td>"
            f"<td>{r['latency_p95_ms']}</td>"
            "</tr>"
        )

    history_table_html = f"""
    <table>
      <tr>
        <th>Timestamp</th>
        <th>Total</th>
        <th>Failed</th>
        <th>Error rate</th>
        <th>Lat avg (ms)</th>
        <th>Lat p95 (ms)</th>
      </tr>
      {history_rows}
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

            .charts-container {{
                display: flex;
                justify-content: center;
                align-items: flex-start;
                gap: 28px;
                margin-top: 20px;
                flex-wrap: wrap;
            }}

            .chart-box {{
                width: 520px;
                height: 320px;
                background-color: #fff;
                border: 1px solid #ccc;
                padding: 10px;
                box-sizing: border-box;
                border-radius: 10px;
            }}

            .chart-box.pie {{
                width: 340px;
                height: 340px;
            }}

            canvas {{
                width: 100% !important;
                height: 100% !important;
            }}
        </style>

        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body>
        <form method="POST" action="/run">
            <button type="submit">Relancer un test</button>
        </form>

        <h1>API Monitoring - Open Meteo</h1>
        <p>
          Dernier run: {last_run['timestamp']} |
          Total: {last_run['total_tests']} |
          Failed: {last_run['failed_tests']} |
          Error rate: {last_run['error_rate_percent']}% |
          Lat Avg: {last_run['latency_avg_ms']} ms |
          Lat P95: {last_run['latency_p95_ms']} ms
        </p>

        <div class="charts-container">
            <div class="chart-box"><canvas id="latencyChart"></canvas></div>
            <div class="chart-box"><canvas id="errorChart"></canvas></div>
            <div class="chart-box pie"><canvas id="pieChart"></canvas></div>
        </div>

        <h2>Détails du dernier run</h2>
        {table_html}

        <h2>Historique (20 derniers runs)</h2>
        {history_table_html}

        <script>
            const labels = {timestamps_js};
            const latData = {lat_avgs_js};
            const errData = {error_rates_js};

            new Chart(document.getElementById('latencyChart'), {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: [{{
                        label: 'Latence moyenne (ms)',
                        data: latData,
                        tension: 0.3,
                        pointRadius: 2
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{ y: {{ beginAtZero: true }} }}
                }}
            }});

            new Chart(document.getElementById('errorChart'), {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: [{{
                        label: "Taux d'erreur (%)",
                        data: errData,
                        tension: 0.3,
                        pointRadius: 2
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{ y: {{ beginAtZero: true }} }}
                }}
            }});

            new Chart(document.getElementById('pieChart'), {{
                type: 'pie',
                data: {{
                    labels: ['Success', 'Failed'],
                    datasets: [{{
                        data: [{last_success}, {last_fail}]
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ position: 'bottom' }}
                    }}
                }}
            }});
        </script>
    </body>
    </html>
    """


# Alias demandé par l’énoncé
@app.route("/dashboard")
def dashboard_alias():
    return dashboard()


@app.route("/run", methods=["POST"])
def run_single_test():
    run_all_tests()
    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True)