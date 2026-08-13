import MetaTrader5 as mt5

ok = mt5.initialize(path='C:/Program Files/MetaTrader 5/terminal64.exe',
                    login=263495022, server='Exness-MT5Real37', password='Donsen10!')
print('init:', ok)

for sym in ['BTCUSDc', 'BTCUSDTc']:
    mt5.symbol_select(sym, True)
    info = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    if info is None or tick is None:
        print(sym, '-> symbol tidak tersedia')
        continue
    print(f'{sym}: trade_mode={info.trade_mode} (FULL={mt5.SYMBOL_TRADE_MODE_FULL}, DISABLED={mt5.SYMBOL_TRADE_MODE_DISABLED})')
    print(f'  bid={tick.bid} ask={tick.ask} spread={info.spread} point={info.point} vol_min={info.volume_min}')
    if info.trade_mode != mt5.SYMBOL_TRADE_MODE_FULL:
        print('  -> TIDAK BISA TRADE (disabled)')
        continue
    req = {'action': mt5.TRADE_ACTION_DEAL, 'symbol': sym, 'volume': 0.01,
           'type': mt5.ORDER_TYPE_BUY, 'price': tick.ask, 'sl': tick.ask - 1000 * info.point,
           'tp': tick.ask + 1000 * info.point, 'deviation': 20, 'magic': 10001,
           'comment': 'BTC2TEST', 'type_time': mt5.ORDER_TIME_GTC,
           'type_filling': mt5.ORDER_FILLING_IOC}
    res = mt5.order_send(req)
    print(f'  order BUY -> retcode={res.retcode} {res.comment} order={res.order}')

mt5.shutdown()
