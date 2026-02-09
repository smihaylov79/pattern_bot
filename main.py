from core.data_feed import init_mt5, shutdown_mt5
from core.engine import BotEngine
from pathlib import Path
import yaml


def load_settings():
    path = Path(__file__).resolve().parent / "config" / "settings.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_symbols():
    path = Path(__file__).resolve().parent / "config" / "symbols.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)["symbols"]


def main():
    init_mt5()

    settings = load_settings()
    symbols = load_symbols()

    tf_ltf = settings["data"]["timeframe"]
    tf_htf = "M15"  # later: use HTF_MAP
    bars = settings["data"]["bars_history"]

    bot = BotEngine(
        symbols=symbols,
        timeframe=tf_ltf,
        htf=tf_htf,
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
