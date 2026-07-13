# DLineBot — AI-XAU-BOT Trading System

## Overview
Automated trading bot untuk **XAUUSD** di **MetaTrader 5** (Exness cent account). Menggabungkan **XGBoost AI predictions**, **market regime detection**, **real-time fundamental analysis**, **multi-timeframe confirmation**, dan **smart scalping** dalam satu live trading engine. Dilengkapi Telegram notifications, database logging, dan web dashboard.

---

## Architecture

```
live.py                     # Entry point — starts dashboard + live runner
dashboard.py                # Standalone dashboard server (port 8000)
manual_order.py             # CLI manual order with SL, TP1, TP2
main.py                     # Training pipeline

app/
  live/
    live_engine.py           # Main orchestration engine (10s cycle)
    live_runner.py           # Loop wrapper
    scheduler.py             # Candle scheduler
    *_view.py                # Console display views

  mt5/
    session.py               # MT5 connection manager
    order_builder.py         # Market order builder (BUY/SELL)
    order_sender.py          # Order validation + send
    order_validator.py       # Order validation
    response_parser.py       # MT5 order response parser
    position_manager.py       # Position query + summary
    trader.py                # MT5 helper (symbol info, tick, positions)
    parted_order.py          # Manual/auto order with SL, TP1, TP2
    account_manager.py       # Account info
    history_manager.py       # Deal history (today, summary)

  trading/
    auto_trader.py           # Auto trade executor
    position_sizing.py       # ATR-based lot size, SL, TP
    decision_engine.py       # AI signal -> trade decision
    trade_filter.py          # Spread + volatility filter
    trade_scorer.py          # Multi-factor trade score
    risk_manager.py          # SL/TP from points
    daily_risk_manager.py    # Daily trade limit + loss/profit cap
    position_filter.py       # Prevent duplicate positions
    equity_manager.py        # Equity tracking (SAFE/WARNING/DANGER)
    drawdown_manager.py      # Peak-to-current drawdown blocker
    news_filter.py           # ForexFactory High Impact news blocker
    market_regime.py         # EMA20/50/200 trend + ADX strength
    confidence_manager.py    # AI confidence threshold
    spread_filter.py         # Max spread check
    volatility_filter.py     # Min ATR check
    multi_tf_confirmation.py # Higher TF trend alignment (M1 -> M5, M15)
    smart_scalping.py        # Scalp engine (momentum, speed, liquidity, etc.)
    break_even.py            # Break-even SL management
    trailing_stop_manager.py # Trailing stop logic
    exit_manager.py          # AI-based exit
    time_exit.py             # Max holding time exit
    ai_exit.py               # ML-based exit signal
    emergency_exit.py        # Max loss per trade / daily
    smart_position_manager.py # Multi-level position management
    performance_manager.py   # Performance summary
    learning_manager.py      # Closed trade -> model retrain
    trade_learner.py         # Adaptive feature weights + retrain
    model_version.py         # Model version tracking
    fundamental_trader.py    # 15-min auto trade based on fundamental bias

  strategy/
    daily_trend_engine.py    # Daily fundamental bias (base class)
    daily_trend_view.py      # Console display
    real_fundamental_engine.py # Real-time fundamental engine (DXY, US10Y, news)

  ai/
    model_loader.py          # XGBoost model loader
    predictor.py             # Prediction engine
    trainer.py               # XGBoost trainer

  notification/
    telegram_notifier.py     # Synchronous Telegram sender (requests)

  database/
    session.py               # SQLAlchemy engine (SQLite/PostgreSQL)
    models.py                # TradeLog, EquitySnapshot, LearningRecord
    db_logger.py             # Database logger

  web_dashboard/
    main.py                  # FastAPI server + HTML dashboard
```

---

## Key Features — Penjelasan Detail

### 1. AI Prediction (XGBoost)

**Cara kerja:**
Bot menggunakan model **XGBoost** yang sudah dilatih untuk memprediksi arah harga XAUUSD dalam 1 candle ke depan.

- **Model**: `xgboost_xauusd_m1.joblib` — dilatih khusus untuk timeframe M1
- **Features**: 50+ indikator teknikal (RSI, MACD, Bollinger Bands, Moving Averages, ATR, Stochastic, dll)
- **Threshold**: Minimal confidence 60% untuk scalping, 70% untuk swing — di bawah itu sinyal ditolak
- **Output**: Prediksi BUY, SELL, atau HOLD + confidence score (0-100%)
- **Adaptive Learning**: `TradeLearner` menyimpan feature weights yang menyesuaikan berdasarkan hasil trading real — fitur yang sering benar dapat bobot lebih tinggi

**Alur**: Data market → indicator engine → feature extraction → XGBoost predict → confidence check

### 2. Trading Filters (Semua Harus Lulus)

Sebelum eksekusi, bot melewati **9 filter berantai**. Jika SATU saja gagal, trade dibatalkan:

| Filter | Logic | Kenapa Penting |
|--------|-------|----------------|
| **Spread** | Spread saat ini <= max_spread (300 pts Exness) | Spread tinggi = biaya masuk mahal, sulit profit |
| **Volatility (ATR)** | ATR >= min_atr (0.5) | Pasar terlalu sepi = gerak harga minim |
| **Trade Score** | Multi-factor score >= threshold | Sintesis semua faktor jadi skor tunggal |
| **Daily Risk** | Trade hari ini < 50 & loss < -300 & profit < +200 | Batasi exposure harian |
| **Position Filter** | Belum ada posisi BUY/SELL untuk XAUUSDc | Hindari overlapping posisi |
| **Higher TF** | M5 & M15 harus searah sinyal | Konfirmasi trend dari timeframe lebih besar |
| **News Filter** | Tidak ada High Impact news dalam 30 menit | News besar bisa bikin harga loncat tak terduga |
| **Drawdown** | Drawdown dari peak < 7% | Stop trading kalau drawdown sudah parah |
| **AI Confidence** | Confidence prediksi >= 60% | Hanya trade kalau AI yakin |

**Alur**: Setiap cycle, filter dicek berurutan. Jika lolos semua → lanjut ke eksekusi.

### 3. Smart Scalping Engine

Engine khusus untuk membaca **micro-structure** pasar M1, terdiri dari 6 komponen:

- **Momentum**: Kekuatan dorongan harga — apakah buyer/seller dominan?
- **Speed**: Kecepatan perubahan harga — percepatan/perlambatan
- **Liquidity**: Volume order di orderbook — cukup dalam untuk entry?
- **Fake Breakout**: Deteksi false breakout — harga tembus level lalu balik
- **Session**: Bias berdasarkan sesi trading (Asia, London, New York)
- **Impulse**: Lonjakan harga mendadak — entry opportunity?

**Output**: Score 0-100 + grade (A/B/C/D/E) + direction + action (TRADE/WAIT). Digunakan oleh TradeScorer untuk final decision.

### 4. Market Regime Detection

Menentukan **mode pasar** saat ini:

- **Trend Direction**: Dari alignment 3 EMA (20, 50, 200)
  - EMA20 > EMA50 > EMA200 = **BULLISH** (uptrend kuat)
  - EMA20 < EMA50 < EMA200 = **BEARISH** (downtrend kuat)
  - Saling silang = **RANGING** (sideways)
- **Strength**: Dari ADX (Average Directional Index)
  - ADX > 25 = Strong
  - ADX 20-25 = Medium
  - ADX < 20 = Weak
- **Mode**: TREND atau RANGING — mempengaruhi position sizing (risk lebih besar di trend, lebih kecil di ranging)

**Output**: Digunakan oleh PositionSizingAI untuk menyesuaikan lot size + oleh TradeScorer untuk confidence multiplier.

### 5. Real-Time Fundamental Engine

Menggantikan data fundamental statis dengan **data real-time** dari 3 sumber:

**a. DXY (US Dollar Index)**
- Sumber: Yahoo Finance (`DX-Y.NYB`)
- Logic: Jika DXY naik → USD menguat → XAU bearish. Jika DXY turun → USD melemah → XAU bullish
- Data: Price, change, change%, direction

**b. US10Y Yield**
- Sumber: Yahoo Finance (`^TNX`)
- Logic: Jika yield naik → opportunity cost emas naik → XAU bearish. Yield turun → XAU bullish
- Data: Yield %, change, direction

**c. Economic Calendar (ForexFactory)**
- Sumber: `https://nfs.faireconomy.media/ff_calendar_thisweek.json`
- Ambil event High Impact hari ini
- Interpretasi otomatis: CPI, NFP, GDP, Interest Rate, Retail Sales, dll
- Bandingkan actual vs forecast → bullish/bearish untuk XAU

**Output**: Bias (STRONG BULLISH/BULLISH/NEUTRAL/BEARISH/STRONG BEARISH), confidence, score, reasons list.

**Cache**: 15 menit. Dikirim ke Telegram tiap 15 menit sebagai sinyal fundamental.

### 6. Manual Order (SL, TP1, TP2)

**Masalah**: MT5 hanya mendukung 1 TP per posisi. Untuk partial take-profit, perlu 2 posisi terpisah.

**Solusi**: `PartedOrder` — membagi 1 lot jadi 2 order:

```
Total Lot: 0.02
  Order 1: 0.01 (50%) + SL = 4050 + TP1 = 4040  ← profit target 1
  Order 2: 0.01 (50%) + SL = 4050 + TP2 = 4035  ← profit target 2
```

**Cara pakai:**
- **CLI**: `python manual_order.py` — masukkan symbol, signal, lot, SL, TP1, TP2
- **Dashboard**: Tab "Manual Order" — isi form, klik KIRIM ORDER
- Entry price: isi untuk limit order, kosongkan untuk market order (pakai ask/bid)

**Notifikasi**: Telegram otomatis — "MANUAL BUY/SELL" + detail entry, SL, TP1, TP2, ticket number.

**Logging**: 2 entry di `trade_log` (satu untuk TP1, satu untuk TP2) + dashboard langsung update.

### 7. 15-Minute Fundamental Auto Trade

Setiap 15 menit, bot mengecek fundamental signal dan **otomatis membuka posisi** jika kondusif.

**Alur:**
1. `RealFundamentalEngine.analyze()` → dapat bias + confidence
2. `FundamentalTrader.should_trade()` → cek:
   - Bias bukan NEUTRAL
   - Confidence >= 50%
   - Tidak ada posisi terbuka
   - Cooldown 60 menit sudah lewat
3. Jika lolos → hitung SL/TP berdasarkan ATR terkini (M5):
   - SL = 1.5x ATR
   - TP1 = 1.0x ATR
   - TP2 = 2.0x ATR
4. Eksekusi via `PartedOrder` (50% lot @ TP1, 50% lot @ TP2)
5. Log ke database + Telegram notification

**Cooldown**: 60 menit — tidak akan open posisi lagi sebelum interval cooldown selesai.

### 8. Position Management

Setelah posisi terbuka, bot mengelola posisi secara otomatis:

**a. Break Even (BE)**
- Trigger: Profit >= +3 pts (scalp)
- Aksi: Pindahkan SL ke entry price (nol risk)

**b. Trailing Stop (3 level)**
- Loose: Profit >= +5 pts, trail jarak 1 pt
- Tight: Profit >= +8 pts, trail jarak 0.5 pt
- Final: Profit >= +15 pts, trail jarak 0.3 pt

**c. Scale Out**
- Profit >= +10 pts: Tutup 50% posisi
- Sisa posisi lanjut dengan trailing

**d. AI Exit**
- Confidence sinyal berbalik > 80% → exit lebih awal

**e. Time Exit**
- Scalp: 60 menit maksimal
- Swing: 480 menit (8 jam) maksimal

**f. Emergency Exit**
- Loss per trade > max_loss (7.5 pts scalp)
- Daily loss > -150 (Exness)

### 9. Risk Management

**Position Sizing (AI-based):**
```
risk_amount = balance * risk_percent / 100
lot_size = risk_amount / (sl_points * 10)
```

Multiplier yang mempengaruhi lot size:
- **Confidence**: 0.5x (low) – 1.5x (high confidence)
- **Market Regime**: 1.2x (strong trend), 1.0x (trend), 0.6x (ranging)
- **Volatility**: 0.5x (high ATR) – 1.2x (low ATR)
- **Spread Penalty**: 0.5x (tight spread) – 1.0x (wide spread)

**Risk Parameters (Exness Scalp):**
| Parameter | Value |
|-----------|-------|
| Risk per trade | 1.5% of balance |
| Daily max trades | 50 |
| Daily max loss | -300 USC |
| Daily max profit | +200 USC |
| Max drawdown | 7% (warning 3%, danger 7%) |
| SL multiplier | 1.5x ATR |

### 10. Learning System

**Adaptive Learning Loop:**

1. **Track**: Saat posisi dibuka, simpan feature vector (50+ indikator) + prediksi AI
2. **Evaluate**: Saat posisi closed, bandingkan prediksi vs outcome nyata
3. **Adjust**: Update feature weights — fitur yang akurat naik bobotnya, yang salah turun
4. **Retrain**: Jika ada >= 20 sample baru, retrain model XGBoost dengan data real

**Feature Weights**: Disimpan di `learning_data/feature_weights.json`. Berfungsi sebagai prior knowledge — fitur yang historically akurat akan lebih berpengaruh di prediksi berikutnya.

### 11. Database

**SQLite** (default, zero-config) atau **PostgreSQL** (via DATABASE_URL).

3 tables:

| Table | Content | Contoh Record |
|-------|---------|---------------|
| `trade_log` | Setiap keputusan trading | signal=SELL, conf=76%, action=SELL, status=BLOCKED, reason="Spread terlalu besar" |
| `equity_snapshot` | Snapshot equity tiap cycle | balance=1504.80, equity=1504.80, drawdown=0.0 |
| `learning_record` | Training data untuk retrain | signal=BUY, entry=4042, exit=4048, profit=+6, status=CLOSED |

### 12. Dashboard (FastAPI + Chart.js)

**Arsitektur: pre-compute, single endpoint.**

Bot (`live_engine`) menulis semua data ke `runtime/overview.json` SETIAP cycle.
Dashboard membaca 1 file → 1 API call → instant render.

**Halaman:**
- **Overview**: Balance, equity, floating P/L, drawdown, trades today, open positions table, equity curve chart, trade history, AI signal, scalping engine
- **Analytics**: Win rate, monthly profit bar chart, drawdown curve, trade distribution pie, signal distribution, confidence histogram, hour performance, session performance, heatmap (day x hour), AI accuracy
- **AI Learning**: Feature weights, learning progress chart, learning records table
- **Manual Order**: Form entry + parted order history

**Performance:**
- Overview refresh 15 detik (1 API call)
- Analytics refresh 30 detik (hanya jika tab aktif)
- Learning refresh 45 detik (hanya jika tab aktif)
- Server-side in-memory cache (3-30s TTL)

### 13. Telegram Notifications (@DLineTradeBot)

**Jenis notifikasi:**

| Type | Trigger | Format |
|------|---------|--------|
| **OPEN** | Trade tereksekusi (DRY_RUN/SUCCESS) | Signal, lot, entry, SL, TP, confidence, filter status |
| **CLOSE** | Posisi tertutup | Profit/loss, duration, reason, signal |
| **Fundamental Signal** | Setiap 15 menit | Bias, confidence, score, reasons |
| **Dashboard Summary** | Setiap cycle | Semua filter status, signal, equity |
| **Manual Order** | Via CLI/Dashboard | SL, TP1, TP2, tickets |
| **Startup** | Bot start | URL dashboard |

**Teknis**: Synchronous HTTP via `requests.post()` ke Telegram Bot API. Parse mode HTML untuk formatting.

---

## Files

| File | Purpose |
|------|---------|
| `live.py` | Start bot + dashboard |
| `dashboard.py` | Standalone dashboard (port 8000) |
| `manual_order.py` | CLI manual order (SL, TP1, TP2) |
| `main.py` | Model training pipeline |
| `.env` | Secrets (MT5, Telegram, broker config) |
| `app/config/settings.py` | Environment variable loader |
| `runtime/overview.json` | Pre-computed dashboard data (written by live_engine) |
| `runtime/scalping.json` | Smart scalping snapshot |
| `data/dlinebot.db` | SQLite database |
| `models/xgboost_xauusd_m1.joblib` | Trained XGBoost model |

---

## Setup & Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure .env
MT5_LOGIN=160040915
MT5_PASSWORD=your_mt5_password
MT5_SERVER=Exness-MT5Real20
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
BROKER=exness

# 3. Start bot + dashboard
python live.py

# Dashboard: http://localhost:8000
```

## MT5 Account
- **Broker**: Exness (Standard Cent)
- **Server**: Exness-MT5Real20
- **Login**: 160040915
- **Symbol**: XAUUSDc
- **Leverage**: 1:2000
- **Balance**: ~1,416 USC

## Key Parameters (Exness Scalp Profile)
| Parameter | Value |
|-----------|-------|
| Timeframe | M1 |
| Max Spread | 300 pts |
| SL Points | 5 |
| RR Ratio | 1.5 |
| Risk per Trade | 1.5% |
| Daily Max Trades | 50 |
| Time Exit | 60 min |
| Drawdown Max | 7% |
| Confidence Min | 0.60 |
