"""
Multi-Server POS Architecture
===============================
Run multiple server instances:
  - AUTH-1: Handles authentication only (port 8081)
  - API-1:  Handles POS business logic (port 8082)
  - API-2:  Handles POS business logic (port 8083)

Usage:
  python run_servers.py              # Start all local servers
  python run_servers.py --auth-only  # Start only auth server
  python run_servers.py --api-only   # Start one API server
  python run_servers.py --api-server 2  # Start API server with ID 2
"""

import os
import sys
import argparse
import logging
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("multi_server")


def wait_for_server(url, timeout=30):
    """Wait for a server to become healthy."""
    import requests
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
    logger.info(f"[{server_id}] Server started on port {port}")
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="POS Multi-Server Launcher")
    parser.add_argument("--auth-only", action="store_true", help="Start only auth server")
    parser.add_argument("--api-only", action="store_true", help="Start only one API server")
    parser.add_argument("--api-server", type=int, default=1, help="API server number (1 or 2)")
    parser.add_argument("--lb-only", action="store_true", help="Start only load balancer")
    parser.add_argument("--lb-urls", type=str, default="", help="Comma-separated backend URLs for LB")
    args = parser.parse_args()

    if args.lb_only:
        from multi_server_lb import create_load_balancer
        lb_urls = args.lb_urls.split(",") if args.lb_urls else []
        if not lb_urls:
            print("ERROR: --lb-urls required with --lb-only")
            sys.exit(1)
        lb_app = create_load_balancer(lb_urls)
        print("Starting Load Balancer on port 8080...")
        start_server(lb_app, 8080, "LB")
        return

    if not args.api_only and not args.auth_only:
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
        auth_app = create_app()
        print(f"[AUTH-1] Starting auth server on port {auth_port}...")
        t1 = threading.Thread(target=start_server, args=(auth_app, auth_port, "AUTH-1"), daemon=True)
        t1.start()

        if wait_for_server(f"http://localhost:{auth_port}"):
            print(f"[AUTH-1] Auth server ready on http://localhost:{auth_port}")
        else:
            print(f"[AUTH-1] WARNING: Auth server did not respond to health check")

        # API Server 1
        os.environ["SERVER_MODE"] = "api"
        os.environ["SERVER_ID"] = "API-1"
        os.environ["PORT"] = str(api1_port)
        api1_app = create_app()
        print(f"[API-1] Starting API server 1 on port {api1_port}...")
        t2 = threading.Thread(target=start_server, args=(api1_app, api1_port, "API-1"), daemon=True)
        t2.start()

        if wait_for_server(f"http://localhost:{api1_port}"):
            print(f"[API-1] API server 1 ready on http://localhost:{api1_port}")

        # API Server 2
        os.environ["SERVER_ID"] = "API-2"
        os.environ["PORT"] = str(api2_port)
        api2_app = create_app()
        print(f"[API-2] Starting API server 2 on port {api2_port}...")
        t3 = threading.Thread(target=start_server, args=(api2_app, api2_port, "API-2"), daemon=True)
        t3.start()

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
            while t1.is_alive() and t2.is_alive() and t3.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down servers...")
            sys.exit(0)
        return

    if args.auth_only:
        os.environ["SERVER_MODE"] = "auth"
        os.environ["SERVER_ID"] = "AUTH-1"
        port = int(os.environ.get("PORT", "8081"))
        auth_app = create_app()
        print(f"Starting Auth Server on port {port}...")
        start_server(auth_app, port, "AUTH-1")
        return

    if args.api_only:
        os.environ["SERVER_MODE"] = "api"
        server_num = args.api_server
        os.environ["SERVER_ID"] = f"API-{server_num}"
        port = int(os.environ.get("PORT", f"808{server_num + 1}"))
        api_app = create_app()
        print(f"Starting API Server {server_num} on port {port}...")
        start_server(api_app, port, f"API-{server_num}")
        return


if __name__ == "__main__":
    main()
