import uvicorn
import socket
import os
from pathlib import Path
from dotenv import load_dotenv, set_key

load_dotenv()

ENV_PATH = Path(".env")


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def start_ngrok(port):
    try:
        from pyngrok import ngrok

        auth_token = os.getenv("NGROK_AUTH_TOKEN")
        if auth_token:
            ngrok.set_auth_token(auth_token)

        public_url = ngrok.connect(port, "http").public_url
        return public_url
    except Exception as e:
        print(f"ngrok gagal: {e}")
        return None


if __name__ == "__main__":
    port = 8000
    local_ip = get_local_ip()
    ngrok_url = start_ngrok(port)

    print("=" * 60)
    print("DASHBOARD")
    print("=" * 60)
    print(f"Local : http://{local_ip}:{port}")
    if ngrok_url:
        print(f"Public: {ngrok_url}")
        set_key(ENV_PATH, "DASHBOARD_URL", ngrok_url)
        print("(URL otomatis tersimpan ke .env)")
    else:
        print(f"HP    : http://{local_ip}:{port}")
        set_key(ENV_PATH, "DASHBOARD_URL", f"http://{local_ip}:{port}")
    print("=" * 60)

    uvicorn.run(
        "app.web_dashboard.main:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )
