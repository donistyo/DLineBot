import uvicorn
import socket
import os
import atexit
import threading
from pathlib import Path
from dotenv import load_dotenv, set_key

load_dotenv()

ENV_PATH = Path(".env")
NGROK_BIN = Path("C:/Users/ADSS/AI-XAU-BOT/ngrok/ngrok.exe")

_runner = None
_runner_thread = None


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def start_engine():
    global _runner, _runner_thread
    if _runner and _runner.running:
        return
    from app.live.live_runner import LiveRunner
    _runner = LiveRunner(interval=10, symbol="XAUUSDc", timeframe="M1", bars=2000, dry_run=False, mode="scalp")
    _runner_thread = threading.Thread(target=_runner.start, daemon=True)
    _runner_thread.start()
    print("Live engine started.")


def stop_engine():
    global _runner
    if _runner and _runner.running:
        _runner.stop()
        print("Live engine stopped.")
        return True
    return False


public_url = None


def start_tunnel(port):
    global public_url
    try:
        from pyngrok import ngrok, conf
        conf.get_default().ngrok_path = str(NGROK_BIN)
        tunnel = ngrok.connect(port, "http")
        public_url = tunnel.public_url
        print(f"Public: {public_url}")
        set_key(ENV_PATH, "DASHBOARD_URL", public_url)
        atexit.register(lambda: ngrok.kill())
        return public_url
    except Exception as e:
        print(f"ngrok gagal: {e}")
        return None


if __name__ == "__main__":
    port = 8000
    local_ip = get_local_ip()

    print("=" * 60)
    print("DASHBOARD + LIVE ENGINE")
    print("=" * 60)
    print(f"Local : http://{local_ip}:{port}")

    url = start_tunnel(port)
    if not url:
        print(f"HP    : http://{local_ip}:{port}")
        set_key(ENV_PATH, "DASHBOARD_URL", f"http://{local_ip}:{port}")

    start_engine()
    atexit.register(stop_engine)

    print("=" * 60)

    uvicorn.run(
        "app.web_dashboard.main:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )
