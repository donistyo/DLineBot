import MetaTrader5 as mt5

ok = mt5.initialize(path='C:/Program Files/MetaTrader 5/terminal64.exe',
                    login=263495022, server='Exness-MT5Real37', password='Donsen10!')
print('init:', ok)

sym = 'BTCUSDc'
mt5.symbol_select(sym, True)
info = mt5.symbol_info(sym)
tick = mt5.symbol_info_tick(sym)
point = info.point
print('point:', point, 'digits:', info.digits, 'stops_level:', info.trade_stops_level)

ask = tick.ask
tests = {
    'sl_1000pt_5': ask - 1000 * point,
    'sl_5000pt': ask - 5000 * point,
    'sl_50usd': ask - 50,
    'sl_100usd': ask - 100,
    'sl_500usd': ask - 500,
}

for name, sl in tests.items():
    req = {'action': mt5.TRADE_ACTION_DEAL, 'symbol': sym, 'volume': 0.01,
           'type': mt5.ORDER_TYPE_BUY, 'price': ask, 'sl': sl, 'tp': ask + 500,
           'deviation': 20, 'magic': 10001, 'comment': 'SLTEST',
           'type_time': mt5.ORDER_TIME_GTC, 'type_filling': mt5.ORDER_FILLING_IOC}
    res = mt5.order_send(req)
    print(f'{name}: SL={sl} -> retcode {res.retcode} {res.comment} order={res.order}')

mt5.shutdown()
