import MetaTrader5 as mt5
from app.data.collector import Collector
from app.indicators.engine import IndicatorEngine
from datetime import datetime
import time

mt5.initialize()
c = Collector()
ie = IndicatorEngine()

print("Monitoring sinyal entry... (cek tiap 30 detik)")
print("Kriteria: ADX > 20 + harga dekat EMA20 + scalp score >= 30")
print("Tekan Ctrl+C untuk stop")
print()

while True:
    try:
        tick = mt5.symbol_info_tick("XAUUSDc")
        bid = tick.bid
        ask = tick.ask
        
        df = c.load("XAUUSDc", "M5", 200)
        if df is not None and len(df) > 0:
            df = ie.calculate(df)
            r = df.iloc[-1]
            adx = r["ADX"]
            rsi = r["RSI"]
            ema20 = r["EMA20"]
            close = r["close"]
            trend = "UP" if close > ema20 else "DOWN"
            
            now = datetime.now().strftime("%H:%M:%S")
            signal = "TUNGGU"
            
            if adx > 20 and trend == "UP" and rsi < 60:
                signal = "BUY"
            elif adx > 20 and trend == "DOWN" and rsi > 40:
                signal = "SELL"
            elif rsi > 70:
                signal = "OVB (siap turun)"
            elif rsi < 30:
                signal = "OVS (siap naik)"
            elif close < ema20 and abs(close - ema20) < 1:
                signal = "DEKAT EMA (tunggu pantul)"
            elif close > ema20 and abs(close - ema20) < 1:
                signal = "DEKAT EMA (tunggu tembus)"
            
            print(now + " | Bid=" + str(round(bid,2)) + " | M5: " + trend + " ADX=" + str(round(adx,1)) + " RSI=" + str(round(rsi,1)) + " => " + signal)
            
            if signal in ("BUY", "SELL"):
                print("")
                print("=== SINYAL ENTRY " + signal + " ===")
                print("Harga: " + str(round(bid,2)) + " / " + str(round(ask,2)))
                print("ADX: " + str(round(adx,1)) + " (ada momentum)")
                print("Lot: 0.01")
                print("================================")
                print("")
        
    except Exception as e:
        print("Error: " + str(e))
    
    time.sleep(30)
