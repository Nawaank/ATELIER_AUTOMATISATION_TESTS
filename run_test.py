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

    data_ok = None
    if resp is not None:
        try:
            data_ok = resp.json()
        except Exception:
            data_ok = None

    if lat is not None:
        latencies.append(lat)

    # --- Test contract: timezone attendu
    if data_ok is None:
        tests.append({"name": "timezone == Europe/Paris", "status": "FAIL", "latency_ms": None, "details": "No JSON to validate"})
    else:
        tz = data_ok.get("timezone")
        if tz == "Europe/Paris":
            tests.append({"name": "timezone == Europe/Paris", "status": "PASS", "latency_ms": None, "details": "-"})
        else:
            tests.append({"name": "timezone == Europe/Paris", "status": "FAIL", "latency_ms": None, "details": f"Got {tz}"})

    # --- Test contract: champs météo clés (types)
    if data_ok is None:
        tests.append({"name": "current_weather types", "status": "FAIL", "latency_ms": None, "details": "No JSON to validate"})
    else:
        cw = data_ok.get("current_weather", {})
        problems = []
        if not isinstance(cw.get("time"), str):
            problems.append("time not str")
        if not isinstance(cw.get("is_day"), int):
            problems.append("is_day not int")
        if not isinstance(cw.get("weathercode"), int):
            problems.append("weathercode not int")

        if problems:
            tests.append({"name": "current_weather types", "status": "FAIL", "latency_ms": None, "details": "; ".join(problems)})
        else:
            tests.append({"name": "current_weather types", "status": "PASS", "latency_ms": None, "details": "-"})

    # --- Test contract: current_weather_units présent
    if data_ok is None:
        tests.append({"name": "current_weather_units present", "status": "FAIL", "latency_ms": None, "details": "No JSON to validate"})
    else:
        units = data_ok.get("current_weather_units")
        if isinstance(units, dict) and len(units) > 0:
            tests.append({"name": "current_weather_units present", "status": "PASS", "latency_ms": None, "details": "-"})
        else:
            tests.append({"name": "current_weather_units present", "status": "FAIL", "latency_ms": None, "details": "Missing or not a dict"})

    # --- Test latitude invalide (contrat d'erreur)
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

    # Tableau du dernier run (avec badges)
    table_rows = ""
    for t in last_run["tests"]:
        badge = "pass" if t["status"] == "PASS" else "fail"
        table_rows += (
            f"<tr>"
            f"<td>{t['name']}</td>"
            f"<td><span class='badge {badge}'>{t['status']}</span></td>"
            f"<td>{t.get('latency_ms') if t.get('latency_ms') is not None else '-'}</td>"
            f"<td class='muted'>{t.get('details') or '-'}</td>"
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
        :root {{
          --bg: #0b1220;
          --panel: rgba(255,255,255,.06);
          --border: rgba(255,255,255,.10);
          --text: rgba(255,255,255,.92);
          --muted: rgba(255,255,255,.70);
          --shadow: 0 16px 40px rgba(0,0,0,.35);
          --radius: 16px;
        }}

        * {{ box-sizing: border-box; }}

        body {{
          margin: 0;
          font-family: Inter, Arial, sans-serif;
          background:
            radial-gradient(1000px 500px at 10% 10%, rgba(79,70,229,.35), transparent 55%),
            radial-gradient(900px 500px at 90% 20%, rgba(16,185,129,.18), transparent 55%),
            radial-gradient(900px 500px at 50% 90%, rgba(59,130,246,.16), transparent 55%),
            var(--bg);
          color: var(--text);
        }}

        .container {{
          max-width: 1100px;
          margin: 0 auto;
          padding: 28px 18px 40px;
        }}

        .topbar {{
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          margin-bottom: 16px;
        }}

        h1 {{
          margin: 0;
          font-size: 22px;
          letter-spacing: .2px;
        }}

        .sub {{
          margin: 8px 0 0;
          color: var(--muted);
          font-size: 13px;
        }}

        .card {{
          background: linear-gradient(180deg, var(--panel), rgba(255,255,255,.04));
          border: 1px solid var(--border);
          border-radius: var(--radius);
          box-shadow: var(--shadow);
        }}

        .card.pad {{
          padding: 16px;
        }}

        .kpis {{
          display: grid;
          grid-template-columns: repeat(5, minmax(0, 1fr));
          gap: 12px;
        }}

        .kpi {{
          padding: 12px 12px;
          border-radius: 14px;
          border: 1px solid var(--border);
          background: rgba(255,255,255,.05);
        }}

        .kpi .label {{
          color: var(--muted);
          font-size: 12px;
          margin-bottom: 6px;
        }}

        .kpi .value {{
          font-size: 18px;
          font-weight: 700;
          letter-spacing: .2px;
        }}

        .run-btn {{
          background: linear-gradient(135deg, #4f46e5, #3b82f6);
          color: white;
          border: none;
          padding: 12px 18px;
          font-size: 14px;
          font-weight: 700;
          border-radius: 12px;
          cursor: pointer;
          transition: transform .08s ease, box-shadow .2s ease, filter .2s ease;
          box-shadow: 0 10px 24px rgba(79,70,229,.35);
          white-space: nowrap;
        }}

        .run-btn:hover {{
          filter: brightness(1.06);
          box-shadow: 0 14px 30px rgba(79,70,229,.42);
          transform: translateY(-1px);
        }}

        .run-btn:active {{
          transform: translateY(1px);
          box-shadow: 0 8px 18px rgba(79,70,229,.32);
        }}

        .run-btn:focus {{
          outline: 3px solid rgba(99,102,241,.35);
          outline-offset: 3px;
        }}

        .charts-container {{
          display: grid;
          grid-template-columns: 1.4fr 1.4fr .9fr;
          gap: 12px;
          margin-top: 12px;
        }}

        .chart-box {{
          height: 320px;
          padding: 12px;
        }}

        .chart-title {{
          color: var(--muted);
          font-size: 12px;
          margin: 0 0 8px;
        }}

        canvas {{
          width: 100% !important;
          height: calc(100% - 18px) !important;
        }}

        h2 {{
          margin: 18px 0 10px;
          font-size: 16px;
          color: rgba(255,255,255,.88);
        }}

        table {{
          width: 100%;
          border-collapse: collapse;
          overflow: hidden;
          border-radius: 14px;
          border: 1px solid var(--border);
          background: rgba(255,255,255,.04);
        }}

        th, td {{
          padding: 10px 10px;
          font-size: 13px;
          text-align: left;
          border-bottom: 1px solid rgba(255,255,255,.08);
        }}

        th {{
          color: rgba(255,255,255,.85);
          background: rgba(255,255,255,.06);
          font-weight: 700;
        }}

        tr:hover td {{
          background: rgba(255,255,255,.05);
        }}

        .badge {{
          display: inline-block;
          padding: 4px 10px;
          border-radius: 999px;
          font-size: 12px;
          font-weight: 800;
          letter-spacing: .2px;
          border: 1px solid rgba(255,255,255,.12);
        }}

        .badge.pass {{
          background: rgba(16,185,129,.16);
          color: #a7f3d0;
          border-color: rgba(16,185,129,.22);
        }}

        .badge.fail {{
          background: rgba(239,68,68,.16);
          color: #fecaca;
          border-color: rgba(239,68,68,.22);
        }}

        .muted {{
          color: var(--muted);
        }}

        @media (max-width: 980px) {{
          .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
          .charts-container {{ grid-template-columns: 1fr; }}
          .chart-box {{ height: 300px; }}
        }}
      </style>

      <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>

    <body>
      <div class="container">
        <div class="topbar">
          <div>
            <h1>API Monitoring — Open Meteo</h1>
            <p class="sub">Dernier run : <b>{last_run['timestamp']}</b></p>
          </div>

          <form method="POST" action="/run">
            <button class="run-btn" type="submit">▶ Relancer un test</button>
          </form>
        </div>

        <div class="card pad">
          <div class="kpis">
            <div class="kpi"><div class="label">Total tests</div><div class="value">{last_run['total_tests']}</div></div>
            <div class="kpi"><div class="label">Échecs</div><div class="value">{last_run['failed_tests']}</div></div>
            <div class="kpi"><div class="label">Error rate</div><div class="value">{last_run['error_rate_percent']}%</div></div>
            <div class="kpi"><div class="label">Latence moyenne</div><div class="value">{last_run['latency_avg_ms']} ms</div></div>
            <div class="kpi"><div class="label">Latence p95</div><div class="value">{last_run['latency_p95_ms']} ms</div></div>
          </div>
        </div>

        <div class="charts-container">
          <div class="card chart-box">
            <p class="chart-title">Latence moyenne (ms)</p>
            <canvas id="latencyChart"></canvas>
          </div>

          <div class="card chart-box">
            <p class="chart-title">Taux d'erreur (%)</p>
            <canvas id="errorChart"></canvas>
          </div>

          <div class="card chart-box">
            <p class="chart-title">Dernier run : Success vs Failed</p>
            <canvas id="pieChart"></canvas>
          </div>
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
      </div>
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