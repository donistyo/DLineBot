import MetaTrader5 as mt5

ok = mt5.initialize(path='C:/Program Files/MetaTrader 5/terminal64.exe',
                    login=263495022, server='Exness-MT5Real37', password='Donsen10!')
print('init:', ok)

for sym in ['BTCUSDc', 'XAUUSDc']:
    mt5.symbol_select(sym, True)
    info = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    print(sym, 'trade_mode:', info.trade_mode, 'ask:', tick.ask, 'vol_min:', info.volume_min, 'vol_step:', info.volume_step)
    req = {'action': mt5.TRADE_ACTION_DEAL, 'symbol': sym, 'volume': 0.01,
           'type': mt5.ORDER_TYPE_BUY, 'price': tick.ask, 'deviation': 20,
           'magic': 10001, 'comment': 'DLINETEST', 'type_time': mt5.ORDER_TIME_GTC,
           'type_filling': mt5.ORDER_FILLING_IOC}
    res = mt5.order_send(req)
    print(sym, '-> retcode:', res.retcode, res.comment, 'order:', res.order)

mt5.shutdown()
