#!/usr/bin/env python3
"""
Simple Load Balancer for POS Multi-Server Architecture
Routes:
  /api/auth/* -> AUTH-1 (port 8081)
  /api/*     -> round-robin between API-1 (8082) and API-2 (8083)
"""

from flask import Flask, jsonify, request
import requests
import os
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("load_balancer")

AUTH_BACKENDS = ["http://localhost:8081"]
API_BACKENDS = ["http://localhost:8082", "http://localhost:8083"]
HEALTH_CHECK_INTERVAL = 5

app = Flask(__name__)

auth_healthy = [True] * len(AUTH_BACKENDS)
api_healthy = [True] * len(API_BACKENDS)
auth_idx = [0]
api_idx = [0]


def health_check(url):
    try:
        resp = requests.get(f"{url}/health", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


def start_health_checks():
    def check():
        while True:
            for i, url in enumerate(AUTH_BACKENDS):
                auth_healthy[i] = health_check(url)
            for i, url in enumerate(API_BACKENDS):
                api_healthy[i] = health_check(url)
            time.sleep(HEALTH_CHECK_INTERVAL)
    
    import threading
    t = threading.Thread(target=check, daemon=True)
    t.start()


def get_next_backend(backends, healthy_flags, idx):
    for _ in range(len(backends)):
        i = idx[0] % len(backends)
        idx[0] += 1
        if healthy_flags[i]:
            return backends[i]
    return backends[0] if backends else None


@app.route("/health")
def health():
    return jsonify({"status": "ok", "mode": "load-balancer"})


@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def proxy(path):
    req_path = request.path
    method = request.method
    
    if req_path.startswith("/api/auth") or req_path.startswith("/api/main-admin"):
        backends = AUTH_BACKENDS
        healthy = auth_healthy
        idx = auth_idx
    else:
        backends = API_BACKENDS
        healthy = api_healthy
        idx = api_idx
    
    target = get_next_backend(backends, healthy, idx)
    if not target:
        return jsonify({"error": "No backend servers available"}), 503
    
    try:
        resp = requests.request(
            method=method,
            url=f"{target}{req_path}",
            headers={k: v for k, v in request.headers if k != "Host"},
            data=request.get_data(),
            cookies=request.cookies,
            params=request.args,
            timeout=30,
            allow_redirects=False,
        )
        return (resp.content, resp.status_code, dict(resp.headers))
    except Exception as e:
        logger.error(f"Proxy error to {target}: {e}")
        return jsonify({"error": "Backend unavailable", "details": str(e)}), 503


if __name__ == "__main__":
    start_health_checks()
    port = int(os.environ.get("PORT", "8080"))
    logger.info(f"Load Balancer starting on port {port}")
    logger.info(f"Auth backends: {AUTH_BACKENDS}")
    logger.info(f"API backends: {API_BACKENDS}")
    app.run(host="0.0.0.0", port=port, threaded=True)
