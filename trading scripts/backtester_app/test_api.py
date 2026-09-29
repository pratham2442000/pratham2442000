import sys
import os
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
from app import app

client = TestClient(app)

def test_endpoints():
    print("Testing /api/health...")
    r = client.get("/api/health")
    assert r.status_code == 200, f"Health check failed: {r.text}"
    print("✓ Health check OK:", r.json())

    print("\nTesting /api/presets...")
    r = client.get("/api/presets")
    assert r.status_code == 200
    presets = r.json()
    assert len(presets) >= 4
    print(f"✓ Presets OK: {len(presets)} presets available")

    print("\nTesting /api/search?q=nifty...")
    r = client.get("/api/search?q=nifty")
    assert r.status_code == 200
    results = r.json()
    assert len(results) > 0
    print(f"✓ Search OK: {len(results)} matches for 'nifty'")

    print("\nTesting /api/backtest with Gold (Daily vs 1st)...")
    payload = {
        "symbol": "GC=F",
        "startDate": "2023-01-01",
        "endDate": "2023-06-01",
        "budgetMode": "normalized",
        "monthlyBudget": 500.0,
        "strategies": [
            {"id": "daily", "name": "Daily", "frequency": "daily", "amount": 20.0, "step_up_pct": 0.0},
            {"id": "monthly_1st", "name": "1st of Month", "frequency": "monthly_1st", "amount": 500.0, "step_up_pct": 0.0}
        ]
    }
    r = client.post("/api/backtest", json=payload)
    assert r.status_code == 200, f"Backtest failed: {r.text}"
    data = r.json()
    assert data["success"] is True
    assert "result" in data
    assert len(data["result"]["strategies"]) == 2
    print("✓ Backtest API OK. Winner:", data["result"]["comparison"]["winnerName"])

    print("\nTesting Frontend HTML delivery...")
    r = client.get("/")
    assert r.status_code == 200
    assert "AlphaDCA" in r.text
    assert "mainChart" in r.text
    print("✓ Frontend delivery OK")

    print("\nTesting /api/strategies (Dynamic Strategy Registry)...")
    r = client.get("/api/strategies")
    assert r.status_code == 200
    strats = r.json()
    assert len(strats) >= 5
    strat_ids = [s["id"] for s in strats]
    print(f"✓ Strategies Registered ({len(strats)}):", strat_ids)
    assert "daily" in strat_ids
    assert "buy_the_dip" in strat_ids
    assert "custom_mid_month_dip" in strat_ids  # user custom plugin auto-discovered!

    print("\nTesting /api/backtest with Buy The Dip Strategy...")
    payload_dip = {
        "symbol": "GC=F",
        "startDate": "2023-01-01",
        "endDate": "2023-06-01",
        "budgetMode": "normalized",
        "monthlyBudget": 500.0,
        "strategies": [
            {"id": "monthly_1st", "name": "1st of Month", "frequency": "monthly_day", "amount": 500.0, "step_up_pct": 0.0, "params": {"day_of_month": 1}},
            {"id": "dip_buyer", "name": "Buy The Dip (-5%)", "frequency": "buy_the_dip", "amount": 500.0, "step_up_pct": 0.0, "params": {"dip_pct": 5.0, "lookback_days": 20, "dip_multiplier": 1.5}},
            {"id": "custom", "name": "Custom Mid-Month Dip", "frequency": "custom_mid_month_dip", "amount": 500.0, "step_up_pct": 0.0, "params": {"bonus_multiplier": 1.5}}
        ]
    }
    r = client.post("/api/backtest", json=payload_dip)
    assert r.status_code == 200, f"Dip Backtest failed: {r.text}"
    data = r.json()
    assert len(data["result"]["strategies"]) == 3
    print("✓ Custom & Smart Strategies Backtest OK. Winner:", data["result"]["comparison"]["winnerName"])

    print("\nTesting Security Headers...")
    r_front = client.get("/")
    assert "Content-Security-Policy" in r_front.headers
    assert r_front.headers["X-Content-Type-Options"] == "nosniff"
    assert r_front.headers["X-Frame-Options"] == "SAMEORIGIN"
    print("✓ Security Headers OK")

    print("\n🎉 ALL API, CUSTOM STRATEGY, & SECURITY TESTS PASSED!")

if __name__ == "__main__":
    test_endpoints()
