from core.data_feed import init_mt5, shutdown_mt5
from core.engine import BotEngine
from pathlib import Path
import yaml


def load_settings():
    path = Path(__file__).resolve().parent / "config" / "settings.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_symbol_config():
    path = Path(__file__).resolve().parent / "config" / "symbols.yaml"
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    symbols = data.get("symbols", [])
    settings = data.get("symbol_settings", {})

    return symbols, settings


def main():
    init_mt5()

    settings = load_settings()
    symbols, symbol_settings = load_symbol_config()


    tf = settings["data"]["timeframe"]
    tf_htf = settings["data"]["htf"]
    tf_ltf = settings["data"]["ltf"]
    bars = settings["data"]["bars_history"]

    bot = BotEngine(
        symbols=symbols,
        symbol_settings=symbol_settings,
        timeframe=tf,
        htf=tf_htf,
        ltf=tf_ltf,
        bars=bars,
        settings=settings,
        sleep_time=10,
    )

    try:
        bot.run()
    except KeyboardInterrupt:
        print("Bot stopped manually.")
    finally:
        shutdown_mt5()


if __name__ == "__main__":
    main()
