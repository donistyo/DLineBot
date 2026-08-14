# PANDUAN AKTIVASI VPS EXNESS & DAPAT KREDENSIAL RDP

Panduan ini untuk mendapatkan VPS gratis Exness (Windows Server 2019) dan kredensial
RDP (IP, login, password) agar bot DLineBot bisa jalan 24 jam tanpa PC nyala.

> VPS Exness GRATIS, tapi ada syarat saldo/volume akun. Cek dulu di langkah 1.

---

## 1. CEK KUALIFIKASI VPS

1. Buka Wilayah Pribadi Exness: https://my.exness.com/pa/deposit
2. Login dengan akun yang sama dengan trading (Real20).
3. Masuk menu **Pengaturan** (Settings).
4. Pilih **Server Pribadi Virtual** (Virtual Private Server).
5. Di halaman itu akan terlihat kriteria syarat:
   - **Saldo akun**: jumlah deposit yang dibutuhkan, ATAU
   - **Volume trading**: total lot yang harus ditradingkan dalam periode tertentu.
6. Kalau sudah memenuhi salah satu, tombol **"Minta hosting VPS"** akan aktif.

> Catatan umum: untuk tipe akun Pro/Raw/Zero biasanya butuh saldo sekitar **$1000**
> atau volume trading tertentu. Saldo kamu sekarang ±$227 — kemungkinan belum cukup.
> Opsi alternatif ada di bagian paling bawah panduan ini.

---

## 2. AJUKAN (REQUEST) VPS

1. Di halaman yang sama (Pengaturan → Server Pribadi Virtual), klik
   **"Minta hosting VPS"** (Request VPS hosting).
2. Tunggu sampai VPS aktif. Status di kiri atas berubah jadi **"Online"**.
   Biasanya butuh beberapa menit sampai beberapa jam.
3. Jika perlu deposit/trading untuk memenuhi syarat, lakukan dulu sesuai instruksi,
   lalu kembali ke halaman ini dan minta VPS lagi.

---

## 3. DAPATKAN KREDENSIAL RDP

1. Kembali ke **Pengaturan → Server Pribadi Virtual**.
2. Pastikan status VPS = **Online** (kiri atas layar).
3. Klik tombol **"Login"**.
4. Akan muncul pop-up berisi:
   - **Alamat VPS** (IP address, mis. `103.x.x.x`)
   - **Login VPS** (username, mis. `administrator`)
   - **Kata Sandi VPS** (password)
5. **SALIN & SIMPAN SEKARANG** — password VPS hanya ditampilkan SATU KALI.
   Kalau hilang, kamu harus reset password (langkah 6 di bawah).

---

## 4. TERHUBUNG KE VPS DARI WINDOWS (RDP)

1. Di PC ini tekan `Win` + `R`, ketik `mstsc`, lalu Enter.
   (aplikasi: **Remote Desktop Connection**)
2. Masukkan **Alamat VPS** dari langkah 3, klik **Hubungkan**.
3. Jika ada peringatan sertifikat, klik **Ya** / **Yes**.
4. Masukkan **Login VPS** dan **Kata Sandi VPS**, centang **"Ingat kredensial"** (opsional).
5. Klik **OK** → kamu masuk ke desktop Windows Server 2019.

> **TIPS (penting untuk EA/bot):** sebelum klik Hubungkan, buka tab
> **Local Resources → Lainnya →** centang **Drives** agar bisa salin file dari PC lokal
> lewat clipboard/RDP. Ini memudahkan copy project ke VPS.

---

## 5. SETELAH MASUK VPS (persiapan singkat)

1. **Ganti password VPS** (wajib, disarankan Exness):
   - Klik Start (ikon Windows) → avatar user → **Change account** →
     **Sign-in options** → **Password** → **Change** → isi password baru 2x.
2. **Power plan** (jika tersedia): Control Panel → Power Options →
   **High Performance** (VPS umumnya sudah never-sleep).
3. **Pause Windows Update** 30 hari: Settings → Windows Update →
   Advanced options → Pause updates. (Agar tidak restart tengah malam.)
4. MT5 Exness biasanya SUDAH terpasang di VPS. Pastikan login akun live
   (`160040915 @ Exness-MT5Real20`) dan aktifkan **Algo Trading / Allow live trading**:
   - Tools → Options → Server / Settings → Algo Trading → centang "Allow live trading".

---

## 6. RESET PASSWORD VPS (kalau password hilang)

1. Buka https://my.exness.com/pa/deposit → Pengaturan → Server Pribadi Virtual.
2. Ikuti menu reset password (biasanya via tombol **Reset Password**).
3. Setelah reset, password baru muncul sekali → catat.
4. Guide resmi: https://get.exness.help/hc/id/articles/12493968880540

---

## 7. CARA MEMPERTAHANKAN VPS (agar tidak dicabut)

Exness mencabut akses VPS jika syarat berikut tidak terpenuhi:

1. **Volume trading** dalam 30/90/180 hari (cukup salah satu periode).
2. **Login & trading dari VPS dalam 5 hari** setelah pertama kali akses VPS
   (order tertunda tidak dihitung).
3. **Login & trading minimal 1x dalam 30 hari**, atau VPS dihentikan.

> Artinya: biar bot tetap jalan 24 jam, pastikan akun yang sama dipakai di VPS
> dan biarkan autotrade aktif menjalankan order dari VPS.

---

## 8. LANGKAH SETELAH VPS JADI (lanjutan dari PANDUAN_VPS.md)

Ikuti bagian 4–10 di file `PANDUAN_VPS.md` (copy project, install Python,
setup `.env`, test, dan Task Scheduler auto-start).

---

## 9. ALTERNATIF KALAU SALDO BELUM CUKUP

Kalau VPS Exness gratis belum bisa (saldo/volume belum memenuhi), pakai VPS
berbayar Windows murah. Perkiraan harga:

| Provider | Spek | Harga/bulan |
|---|---|---|
| Contabo Windows VPS | 4 vCPU / 8 GB RAM / 100 GB | ~$12–15 |
| Hostinger VPS | 1 core / 2 GB / 50 GB | ~$5–8 |
| AWS Lightsail (Windows) | 2 vCPU / 4 GB | ~$10 |

> Minimum bot ini: **2 CPU / 4 GB RAM / 50 GB**.
> Instalasi di VPS berbayar SAMA dengan VPS Exness (bukan gratis): MT5 + Python + bot.

---

## RINGKASAN CEPAT

```
1. my.exness.com/pa/deposit → Pengaturan → Server Pribadi Virtual
2. Cek syarat saldo/volume → klik "Minta hosting VPS"
3. Tunggu status Online → klik "Login" → catat IP / login / password (sekali tampil!)
4. mstsc → isi IP → connect → login
5. Ganti password VPS, pastikan MT5 login + Algo Trading ON
6. Lanjut setup bot: PANDUAN_VPS.md (copy project, Python, .env, Task Scheduler)
```
