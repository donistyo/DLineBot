import MetaTrader5 as mt5

ok = mt5.initialize(path='C:/Program Files/MetaTrader 5/terminal64.exe',
                    login=263495022, server='Exness-MT5Real37', password='Donsen10!')
print('init:', ok)
print('posisi BTCUSDc:', len(mt5.positions_get(symbol='BTCUSDc') or []))
print('posisi BTCUSDTc:', len(mt5.positions_get(symbol='BTCUSDTc') or []))

sym = 'BTCUSDc'
mt5.symbol_select(sym, True)
info = mt5.symbol_info(sym)
tick = mt5.symbol_info_tick(sym)
ask = tick.ask
point = info.point

tests = [
    ('SL10 TP10', ask - 10, ask + 10),
    ('SL20 TP20', ask - 20, ask + 20),
    ('SL50 TP50', ask - 50, ask + 50),
    ('SL100 TP100', ask - 100, ask + 100),
    ('SL0 TP0', 0.0, 0.0),
    ('SL10 TP0', ask - 10, 0.0),
]
for name, sl, tp in tests:
    req = {'action': mt5.TRADE_ACTION_DEAL, 'symbol': sym, 'volume': 0.01,
           'type': mt5.ORDER_TYPE_BUY, 'price': ask, 'sl': sl if sl else None,
           'tp': tp if tp else None, 'deviation': 20, 'magic': 10001,
           'comment': 'BTCDIST', 'type_time': mt5.ORDER_TIME_GTC,
           'type_filling': mt5.ORDER_FILLING_IOC}
    res = mt5.order_send(req)
    print(f'{name}: SL={sl or "-"} TP={tp or "-"} -> {res.retcode} {res.comment}')

mt5.shutdown()
