# PANDUAN PINDAH BOT KE VPS (Agar Jalan 24 Jam)

Bot ini (DLineBot) saat ini berjalan di PC lokal. Saat PC **sleep/mati**, engine mati —
yang melindungi posisi hanya SL/TP statis dari broker (seperti kejadian loss -14.4 jam 11:55).
Solusinya: **jalankan bot di VPS** yang tidak pernah tidur.

Rekomendasi: **Windows VPS** (butuh `pywin32`, MT5 API, Task Scheduler yang cocok dipakai di Windows).

---

## 1. PILIH VPS

| Provider | Spek Minimum | Estimasi Harga |
|---|---|---|
| Contabo Windows VPS | 4 vCPU / 8 GB RAM / 100 GB SSD | ~$12-15/bln |
| Hostinger VPS (kVM) | 1 core / 2 GB RAM / 50 GB | ~$5-8/bln |
| DigitalOcean Droplet (Windows) | 1 core / 2 GB RAM | ~$12/bln |
| AWS Lightsail (Windows) | 2 vCPU / 4 GB RAM | ~$10/bln |
| RDP dari broker Exness VPS | Gratis (dengan syarat deposit) | $0 |

> Minimum untuk bot ini: **2 CPU / 4 GB RAM / 50 GB SSD**.
> Kalau punya akun Exness, coba **VPS gratis Exness** dulu (biasanya Windows Server).

---

## 2. LOGIN & SETUP AWAL VPS

1. Login lewat **Remote Desktop (RDP)**: tekan `Win+R` → ketik `mstsc` → isi IP + username/password VPS.
2. Getekan semua browser popup/donasi.
3. Setting **power plan** VPS: `Control Panel → Power Options → High Performance` dan pastikan **never sleep** (VPS umumnya sudah).
4. Matikan Windows Update otomatis yang bisa restart tengah malam:
   - `Settings → Windows Update → Advanced options → Pause updates` (30 hari).

---

## 3. INSTALL METATRADER 5 DI VPS

1. Download MT5 broker Anda (Exness) di VPS: `https://one.exness.com` lalu login.
2. Setelah login di MT5:
   - **Tools → Options → Server**: centang *"Enable News"* (opsional).
   - **Settings → Algo Trading**: aktifkan **"Allow live trading"** untuk akun ini.
   - Pastikan akun yang dipakai **akun live XAUUSDc** sama seperti di PC.

---

## 4. COPY PROJECT KE VPS

Cara paling mudah: buat **file ZIP** dari folder `C:\Users\ADSS\AI-XAU-BOT` di PC, lalu copy ke VPS:

```
Folders yang WAJIB ikut ter-copy:
  app\
  runtime\          (config & data terakhir)
  requirements.txt
  .env              (kredensial MT5 — RAHASIA, jangan share)
  dashboard.py
  start_service.bat
  enable_autotrade.py  (opsional, untuk jadwal pagi)
  wait_flat_off.py     (opsional, untuk auto-off)

Folders yang BOLEH TIDAK ikut (besar & tidak perlu):
  venv\        (akan dibuat ulang di VPS)
  ngrok\       (tidak perlu)
  models\      (bisa di-copy kalau mau analisa fitur AI, opsional)
  datasets\ / backtest\ / notebooks\ / learning_data\ (opsional)
```

> CATATAN `runtime\`:
> - `trade_config.json` → pastikan versi terbaru (sudah ada FAST_TP 2.5 & STALL_EXIT 60s).
> - `auto_trade_enabled.json` → set `{"enabled": true}` setelah semua test.
> - Hapus `wait_flat_off.json` kalau ada (agar tidak mengganggu).

Copy ZIP lewat RDP: klik kanan → paste, atau pakai WinSCP/klipboard RDP.

---

## 5. SETUP PYTHON + DEPENDENSI DI VPS

Buka **PowerShell** di VPS:

```powershell
# 1. Install Python 3.12 (download installer dari python.org, CENTANG "Add to PATH")
python --version

# 2. Masuk ke folder project (sesuaikan path VPS Anda)
cd D:\AI-XAU-BOT

# 3. Buat virtual environment
python -m venv venv

# 4. Aktifkan & install dependencies
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt

# 5. Cek MT5 API terpasang
venv\Scripts\python.exe -c "import MetaTrader5; print('MT5 OK')"
```

> Kalau `pywin32` gagal pasang, install Spring/powertools: `pip install pywin32` ulang, atau
> jalankan `venv\Scripts\python.exe Scripts\pywin32_postinstall.py -install`.

---

## 6. CEK .env DI VPS

File `.env` harus berisi kredensial trading yang SAMA dengan PC:

```
MT5_LOGIN=123456
MT5_PASSWORD=${MasterPassword}
MT5_SERVER=Exness-MT5
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...
DEFAULT_SYMBOL=XAUUSD
```

> **PENTING**: Jangan pernah share `.env` (berisi password MT5).
> Kalau password belum pernah dilihat, generate dari MetaTrader:
> `Tools → Options → Server → Change` atau via portal broker.

---

## 7. TEST BOT DI VPS

Jalankan manual dulu untuk memastikan semuanya jalan:

```powershell
cd D:\AI-XAU-BOT
venv\Scripts\python.exe dashboard.py
```

Cek di konsol:
- `Engine symbol: XAUUSDc`
- `Live engine started.`
- `runtime\overview.json` ter-update setiap ~17 detik (equity & floating PL).

Kalau sudah jalan, tutup jendela ini (Ctrl+C) dan lanjutkan ke langkah otomatis.

---

## 8. AUTO-START DI VPS (Task Scheduler)

Supaya bot start otomatis saat VPS reboot, daftarkan Task Scheduler:

```powershell
# buat task start saat VPS nyala
$action = New-ScheduledTaskAction -Execute "D:\AI-XAU-BOT\venv\Scripts\python.exe" -Argument "dashboard.py" -WorkingDirectory "D:\AI-XAU-BOT"
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "DLineBotAutotrade" -Action $action -Trigger $trigger -RunLevel Highest -Force
```

Uji task:
```powershell
Start-ScheduledTask -TaskName "DLineBotAutotrade"
Get-ScheduledTask -TaskName "DLineBotAutotrade"    # State harus "Running"
```

> Opsional — enable otomatis pagi (mirip `DLineBotEnableMorning` di PC):
> ```powershell
> $a = New-ScheduledTaskAction -Execute "D:\AI-XAU-BOT\venv\Scripts\python.exe" -Argument "D:\AI-XAU-BOT\enable_autotrade.py"
> $t = New-ScheduledTaskTrigger -Daily -At 06:00
> Register-ScheduledTask -TaskName "DLineBotEnableMorning" -Action $a -Trigger $t -Force
> ```

---

## 9. CARA MENGONSUMSI DASHBOARD DARI VPS (opsional)

Dashboard default hanya untuk akses lokal VPS. Untuk melihat dari mana saja:

1. **Cloudflare Tunnel (disarankan, gratis)** — sudah ada `start_tunnel.bat`:
   ```
   cd "C:\Program Files (x86)\cloudflared"
   cloudflared.exe tunnel --url http://localhost:8000
   ```
   Install cloudflared di VPS dari `https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/`.

2. **MoonVPN/Ngrok** — set `NGROK_AUTH_TOKEN` di `.env`.

> Kalau tidak butuh dashboard dari luar, **lewati langkah ini** — bot tetap jalan tanpa dashboard.

---

## 10. VERIFIKASI / CEK KESEHATAN

Setelah semuanya jalan, cek rutin:

| Check | Cara |
|---|---|
| Engine hidup | `Get-Process python` — harus ada 2 proses (launcher + child) |
| Heartbeat | buka `runtime\overview.json`, cek timestamp equity terakhir |
| Posisi | buka MT5 di VPS → Trade tab |
| Trade berjalan | `runtime\close_trace.log` — muncul baris `CLOSE by ...` |

---

## 11. CATATAN PENTING

- **Jaga akun live**: balik lot kecil (0.01) sampai stabil beberapa hari.
- **VPS tetap point of failure**: kalau provider down, engine ikut mati. Tapi jauh lebih stabil dari PC lokal.
- **Sinkronisasi**: kalau mau pindah bolak-balik PC↔VPS, pastikan hanya SATU perangkat yang menjalankan engine (jangan dua-duanya, bisa duplicate trade).
- **Backup**: cadangkan `runtime\` + `.env` berkala (misal mingguan).

---

## RINGKASAN PERINTAH (copy-paste cepat)

```powershell
# Setup awal
cd D:\AI-XAU-BOT
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt

# Test
venv\Scripts\python.exe dashboard.py

# Auto-start saat reboot
$action = New-ScheduledTaskAction -Execute "D:\AI-XAU-BOT\venv\Scripts\python.exe" -Argument "dashboard.py" -WorkingDirectory "D:\AI-XAU-BOT"
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "DLineBotAutotrade" -Action $action -Trigger $trigger -RunLevel Highest -Force
Start-ScheduledTask -TaskName "DLineBotAutotrade"
```