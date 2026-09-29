import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from data_service import fetch_historical_data, search_symbols
from backtest_engine import run_backtest_simulation

def main():
    print("--- 1. Testing Data Service (Gold GC=F) ---")
    df, meta = fetch_historical_data("GC=F", "2023-01-01", "2024-01-01")
    print(f"Success: {meta['name']} ({meta['currency']}) - {len(df)} rows, Latest: {meta['latestPrice']}")

    print("\n--- 2. Testing Data Service (India RELIANCE.NS) ---")
    df_in, meta_in = fetch_historical_data("RELIANCE.NS", "2023-01-01", "2024-01-01")
    print(f"Success: {meta_in['name']} ({meta_in['currency']}) - {len(df_in)} rows, Latest: {meta_in['latestPrice']}")

    print("\n--- 3. Testing Backtest Simulation: Daily vs 1st of Month on Gold ---")
    strategies = [
        {"id": "daily", "name": "Daily Gold", "frequency": "daily", "amount": 25, "step_up_pct": 0},
        {"id": "monthly_1st", "name": "Monthly 1st Gold", "frequency": "monthly_1st", "amount": 500, "step_up_pct": 0}
    ]
    res = run_backtest_simulation(df, strategies, budget_mode="normalized", monthly_budget=500.0)
    for st in res["strategies"]:
        s = st["summary"]
        print(f"{st['name']}: Invested={s['totalInvested']}, Value={s['finalValue']}, Return={s['totalReturnPct']}%, XIRR={s['xirr']}%, Units={s['totalUnits']}")

    print(f"\nComparison: {res['comparison']['insight']}")
    print("\n✓ ALL CORE BACKTEST TESTS PASSED!")

if __name__ == "__main__":
    main()
