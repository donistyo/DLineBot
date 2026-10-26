"""Rotasi log dashboard sebelum proses baru men-truncate file.

Jalankan saat dashboard TIDAK sedang jalan (mis. sebelum restart):
    venv\\Scripts\\python.exe rotate_logs.py
"""

from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"
LIMITS = {"dashboard.log": 100, "dashboard_err.log": 5}
KEEP = 2


def rotate(name, max_mb):
    path = LOG_DIR / name
    try:
        if not path.exists():
            return None
        size_mb = path.stat().st_size / 1048576
        if size_mb < max_mb:
            return None
        oldest = LOG_DIR / f"{name}.{KEEP}"
        if oldest.exists():
            oldest.unlink()
        for i in range(KEEP - 1, 0, -1):
            src = LOG_DIR / f"{name}.{i}"
            if src.exists():
                src.replace(LOG_DIR / f"{name}.{i + 1}")
        path.replace(LOG_DIR / f"{name}.1")
        return size_mb
    except OSError as e:
        print(f"[rotate] {name}: dilewati ({e})")
        return None


if __name__ == "__main__":
    for _name, _max in LIMITS.items():
        _mb = rotate(_name, _max)
        if _mb:
            print(f"[rotate] {_name}: {_mb:.1f} MB -> {_name}.1")
