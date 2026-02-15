import MetaTrader5 as mt5

mt5.initialize()
symbol = 'SUGAR.RAW'

info = mt5.symbol_info(symbol)
price = mt5.symbol_info_tick(symbol)
point = info.point
stop_levels = info.trade_stops_level
price_distance = point * stop_levels
print(price_distance)
current_price = price.bid
sl = current_price - price_distance
tp = current_price + price_distance
print(f'price: {current_price} | sl: {sl} | tp: {tp}')
print(info)

