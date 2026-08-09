"""
Multi-Server POS Architecture
===============================
Run multiple server instances:
  - AUTH-1: Handles authentication only
  - API-1:  Handles POS business logic
  - API-2:  Handles POS business logic
  - LB:     Load balancer (optional, for production)

Usage:
  python run_servers.py              # Start all local servers
  python run_servers.py --auth-only  # Start only auth server
  python run_servers.py --api-only   # Start one API server
  python run_servers.py --api-server 2  # Start API server with ID 2

Environment:
  SERVER_MODE=auth   -> Auth server
  SERVER_MODE=api    -> API server
  SERVER_ID=AUTH-1   -> Server identifier
  PORT=8080          -> Port number
"""

import os
import sys
import argparse
import logging
import signal
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request, g
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("multi_server")


def create_auth_app() -> Flask:
    """Create an auth-only Flask app."""
    # Import the full app factory
    from app import create_app
    app = create_app()
    
    # Remove all non-auth routes
    auth_prefixes = (
        "/api/auth",
        "/api/main-admin",
        "/health",
        "/ready",
    )
    
    original_url_map = list(app.url_map.iter_rules())
    for rule in original_url_map:
        endpoint = rule.endpoint
        path = str(rule)
        
        # Keep auth routes and health checks
        is_auth = any(path.startswith(p) for p in auth_prefixes)
        is_static = path == "/static/<path:filename>"
        
        if not is_auth and not is_static:
            try:
                app.view_functions.pop(endpoint, None)
            except Exception:
                pass
    
    # Add server identification
    @app.before_request
    def identify_server():
        g.server_id = os.environ.get("SERVER_ID", "AUTH-1")
        g.server_mode = "auth"
    
    return app


def create_api_app() -> Flask:
    """Create an API (business logic) Flask app."""
    from app import create_app
    app = create_app()
    
    # Remove auth routes - these are handled by the auth server
    auth_prefixes = (
        "/api/auth",
        "/api/main-admin",
    )
    
    original_url_map = list(app.url_map.iter_rules())
    for rule in original_url_map:
        endpoint = rule.endpoint
        path = str(rule)
        
        is_auth = any(path.startswith(p) for p in auth_prefixes)
        is_static = path == "/static/<path:filename>"
        
        if is_auth and not is_static:
            try:
                app.view_functions.pop(endpoint, None)
            except Exception:
                pass
    
    # Add server identification
    @app.before_request
    def identify_server():
        g.server_id = os.environ.get("SERVER_ID", "API-1")
        g.server_mode = "api"
    
    return app


def create_load_balancer(auth_urls, api_urls):
    """Create a simple load balancer Flask app."""
    app = Flask(__name__)
    
    auth_url_list = auth_urls if isinstance(auth_urls, list) else [auth_urls]
    api_url_list = api_urls if isinstance(api_urls, list) else [api_urls]
    
    auth_idx = [0]
    api_idx = [0]
    
    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "mode": "load-balancer"})
    
    @app.route("/ready")
    def ready():
        return jsonify({"status": "ready", "mode": "load-balancer"})
    
    @app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @app.route("/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    def proxy(path):
        target_urls = None
        req_path = request.path
        
        if req_path.startswith("/api/auth") or req_path.startswith("/api/main-admin"):
            target_urls = auth_url_list
        else:
            target_urls = api_url_list
        
        if not target_urls:
            return jsonify({"error": "No backend servers available"}), 503
        
        # Simple round-robin
        idx = auth_idx[0] if target_urls is auth_url_list else api_idx[0]
        target = target_urls[idx % len(target_urls)]
        if target_urls is auth_url_list:
            auth_idx[0] = (auth_idx[0] + 1) % len(target_urls)
        else:
            api_idx[0] = (api_idx[0] + 1) % len(target_urls)
        
        # Forward request
        try:
            resp = requests.request(
                method=request.method,
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
            logger.error(f"LB proxy error to {target}: {e}")
            return jsonify({"error": "Backend unavailable", "details": str(e)}), 503
    
    return app


def wait_for_server(url, timeout=30):
    """Wait for a server to become healthy."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{url}/health", timeout=2)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def start_server(app, port, server_id):
    """Start a Flask server in a thread."""
    from werkzeug.serving import make_server
    
    server = make_server("0.0.0.0", port, app, threaded=True)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="POS Multi-Server Launcher")
    parser.add_argument("--auth-only", action="store_true", help="Start only auth server")
    parser.add_argument("--api-only", action="store_true", help="Start only one API server")
    parser.add_argument("--api-server", type=int, default=1, help="API server number (1 or 2)")
    parser.add_argument("--lb-only", action="store_true", help="Start only load balancer")
    parser.add_argument("--lb-urls", type=str, default="", help="Comma-separated backend URLs for LB")
    args = parser.parse_args()
    
    servers = []
    
    if args.lb_only:
        lb_urls = args.lb_urls.split(",") if args.lb_urls else []
        if not lb_urls:
            print("ERROR: --lb-urls required with --lb-only")
            sys.exit(1)
        
        # Parse auth vs API URLs
        auth_urls = [u.strip() for u in lb_urls if "/auth" in u or "auth" in u]
        api_urls = [u.strip() for u in lb_urls if "/auth" not in u and "auth" not in u]
        
        if not auth_urls:
            auth_urls = ["http://localhost:8081"]
        if not api_urls:
            api_urls = ["http://localhost:8082", "http://localhost:8083"]
        
        lb_app = create_load_balancer(auth_urls, api_urls)
        print("Starting Load Balancer on port 8080...")
        start_server(lb_app, 8080, "LB")
        return
    
    if not args.api_only and not args.auth_only:
        # Start all servers
        auth_port = int(os.environ.get("AUTH_PORT", "8081"))
        api1_port = int(os.environ.get("API1_PORT", "8082"))
        api2_port = int(os.environ.get("API2_PORT", "8083"))
        
        print("=" * 60)
        print("POS MULTI-SERVER ARCHITECTURE")
        print("=" * 60)
        
        # Auth Server
        os.environ["SERVER_MODE"] = "auth"
        os.environ["SERVER_ID"] = "AUTH-1"
        os.environ["PORT"] = str(auth_port)
        auth_app = create_auth_app()
        print(f"[AUTH-1] Starting auth server on port {auth_port}...")
        t = threading.Thread(target=start_server, args=(auth_app, auth_port, "AUTH-1"), daemon=True)
        t.start()
        servers.append(t)
        
        # Wait for auth server
        if wait_for_server(f"http://localhost:{auth_port}"):
            print(f"[AUTH-1] Auth server ready on http://localhost:{auth_port}")
        else:
            print(f"[AUTH-1] WARNING: Auth server did not respond to health check")
        
        # API Server 1
        os.environ["SERVER_MODE"] = "api"
        os.environ["SERVER_ID"] = "API-1"
        os.environ["PORT"] = str(api1_port)
        api1_app = create_api_app()
        print(f"[API-1] Starting API server 1 on port {api1_port}...")
        t = threading.Thread(target=start_server, args=(api1_app, api1_port, "API-1"), daemon=True)
        t.start()
        servers.append(t)
        
        if wait_for_server(f"http://localhost:{api1_port}"):
            print(f"[API-1] API server 1 ready on http://localhost:{api1_port}")
        
        # API Server 2
        os.environ["SERVER_ID"] = "API-2"
        os.environ["PORT"] = str(api2_port)
        api2_app = create_api_app()
        print(f"[API-2] Starting API server 2 on port {api2_port}...")
        t = threading.Thread(target=start_server, args=(api2_app, api2_port, "API-2"), daemon=True)
        t.start()
        servers.append(t)
        
        if wait_for_server(f"http://localhost:{api2_port}"):
            print(f"[API-2] API server 2 ready on http://localhost:{api2_port}")
        
        print("=" * 60)
        print("All servers started. Press Ctrl+C to stop.")
        print("=" * 60)
        print(f"Auth Server:  http://localhost:{auth_port}")
        print(f"API Server 1: http://localhost:{api1_port}")
        print(f"API Server 2: http://localhost:{api2_port}")
        print("=" * 60)
        
        try:
            while all(t.is_alive() for t in servers):
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down servers...")
            sys.exit(0)
        
        return
    
    if args.auth_only:
        os.environ["SERVER_MODE"] = "auth"
        os.environ["SERVER_ID"] = "AUTH-1"
        port = int(os.environ.get("PORT", "8081"))
        auth_app = create_auth_app()
        print(f"Starting Auth Server on port {port}...")
        start_server(auth_app, port, "AUTH-1")
        return
    
    if args.api_only:
        os.environ["SERVER_MODE"] = "api"
        server_num = args.api_server
        os.environ["SERVER_ID"] = f"API-{server_num}"
        port = int(os.environ.get("PORT", f"808{server_num + 1}"))
        api_app = create_api_app()
        print(f"Starting API Server {server_num} on port {port}...")
        start_server(api_app, port, f"API-{server_num}")
        return


if __name__ == "__main__":
    main()
