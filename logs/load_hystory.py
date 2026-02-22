import MetaTrader5 as mt5
import pandas as pd
import sqlite3
from datetime import datetime, timedelta


def export_history():
    if not mt5.initialize():
        print("MT5 init failed")
        return

    # Determine start date
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT MIN(entry_time) FROM trade_history")
    row = cur.fetchone()

    if row and row[0]:
        start = datetime.fromisoformat(row[0])
    else:
        start = datetime.now() - timedelta(days=5)

    end = datetime.now()

    deals = mt5.history_deals_get(start, end)
    if deals is None:
        print("No deals found")
        return

    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df['time_msc'] = pd.to_datetime(df['time_msc'], unit='ms')

    # Extract signal from comment
    df['signal'] = df['comment'].str.extract(r'([A-Za-z_]+)')
    print(df.columns)

    df.to_sql("trade_history", conn, if_exists="append", index=False)
    conn.close()

    print(f"Exported {len(df)} trades")

if __name__ == "__main__":
    export_history()

