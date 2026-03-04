import sqlite3
import json
import os

# chemin absolu dans ton home sur PythonAnywhere
DB_FILE = os.path.expanduser("~/results.db")

def init_db():
    """Crée la table des runs si elle n'existe pas."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            total_tests INTEGER,
            failed_tests INTEGER,
            error_rate REAL,
            latency_avg REAL,
            latency_p95 REAL,
            tests_json TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_run(run_result):
    """Enregistre un run dans la DB."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO runs (timestamp, total_tests, failed_tests, error_rate, latency_avg, latency_p95, tests_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        run_result["timestamp"],
        run_result["total_tests"],
        run_result["failed_tests"],
        run_result["error_rate_percent"],
        run_result["latency_avg_ms"],
        run_result["latency_p95_ms"],
        json.dumps(run_result["tests"])
    ))
    conn.commit()
    conn.close()

def list_runs(limit=20):
    """Récupère les derniers runs pour le dashboard."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT timestamp, total_tests, failed_tests, error_rate, latency_avg, latency_p95, tests_json FROM runs ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()

    runs = []
    for r in rows:
        runs.append({
            "timestamp": r[0],
            "total_tests": r[1],
            "failed_tests": r[2],
            "error_rate_percent": r[3],
            "latency_avg_ms": r[4],
            "latency_p95_ms": r[5],
            "tests": json.loads(r[6])
        })
    return runs

def get_last_run():
    """Retourne le dernier run, ou un placeholder si aucun."""
    runs = list_runs(limit=1)
    if runs:
        return runs[0]
    else:
        # placeholder vide pour éviter les erreurs dans le dashboard
        return {
            "timestamp": "N/A",
            "total_tests": 0,
            "failed_tests": 0,
            "error_rate_percent": 0,
            "latency_avg_ms": 0,
            "latency_p95_ms": 0,
            "tests": []
        }