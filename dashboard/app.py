from loader import load_db
from layout import render_dashboard, render_signal_explorer

if __name__ == "__main__":
    df = load_db()
    render_dashboard(df)
    render_signal_explorer(df)
