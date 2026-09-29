# AlphaDCA - Multi-Market Stock & Gold Investment Backtester

A backtesting platform built for comparing recurring investment schedules (e.g., **Daily investment vs. Every 1st of the month**, Weekly, Lump Sum, Step-Up SIP) across **US Equities, Indian Equities (NSE/BSE), Global Indices, ETFs, and Gold/Commodities**.

---

## 🚀 Key Features

- **Multi-Market Coverage**:
  - **US Markets**: NYSE / NASDAQ (`AAPL`, `MSFT`, `NVDA`, `SPY`, `QQQ`, `GLD`, `GC=F`)
  - **Indian Markets**: NSE & BSE (`RELIANCE.NS`, `TCS.NS`, `HDFCBANK.NS`, `^NSEI` (Nifty 50), `^BSESN` (Sensex), `GOLDBEES.NS`)
  - **Gold & Commodities**: Gold Futures (`GC=F`), US Gold ETF (`GLD`), Indian Gold BeES (`GOLDBEES.NS`), Silver (`SI=F`)
- **Strategy Comparisons**:
  - Daily Investment (every market trading day)
  - Monthly on any chosen day (1st, 5th, 10th, 15th, 20th, or last day with holiday rollover)
  - Weekly on any chosen weekday (Monday - Friday)
  - Bi-Weekly (twice a month)
  - Lump Sum (Day 1 Buy & Hold benchmark)
  - **Buy The Dip**: Base monthly SIP + automatic bonus accumulation on $X\%$ price drops
  - **200-day SMA Value Booster**: Invests double when price trades below 200 SMA
  - **RSI Oversold Accumulator**: Boosts accumulation when 14-day RSI drops below 30
  - **Value Averaging**: Dynamically adjusts capital to meet steady target portfolio equity
  - **Custom User Strategies**: Drop any new strategy class into `backend/strategies/`!

---

## 🛠️ How to Easily Define a New Strategy in Python

Creating a new strategy takes only **15 lines of code**:

1. Create a `.py` file inside `backend/strategies/` (e.g. `backend/strategies/my_super_strategy.py`).
2. Subclass `BaseStrategy`, define its name, and decorate with `@register_strategy`.
3. Implement `generate_orders()`, returning `{ "YYYY-MM-DD": amount_to_invest }`.

```python
import pandas as pd
from typing import Dict, Any
from .base import BaseStrategy, Parameter
from .registry import register_strategy

@register_strategy
class MyCustomStrategy(BaseStrategy):
    id = "my_custom_strategy"
    name = "My Custom Dip & Momentum Strategy"
    category = "Custom"
    description = "Invests on the 5th of every month, but invests 2x if price dropped > 3% this week."
    
    # Optional parameters that automatically render in the Web UI
    parameters = [
        Parameter(name="multiplier", label="Dip Multiplier", param_type="number", default=2.0, min_value=1.0, max_value=5.0)
    ]

    def generate_orders(self, df: pd.DataFrame, config: Dict[str, Any], budget_mode: str, monthly_budget: float) -> Dict[str, float]:
        orders = {}
        mult = float(config.get("params", {}).get("multiplier", 2.0))
        target_dates = set(df[df["Day"] >= 5].groupby("YearMonth")["Date"].first().dt.strftime("%Y-%m-%d"))

        for idx, row in df.iterrows():
            date_str = row["Date"].strftime("%Y-%m-%d")
            if date_str in target_dates:
                orders[date_str] = monthly_budget * mult
        return orders
```

AlphaDCA will **automatically discover** your new strategy file upon startup, and it will immediately appear in the **Web UI strategy dropdown** with interactive parameter controls!
- **Two Comparison Modes**:
  - **Equal Monthly Budget Mode**: Automatically normalizes daily, weekly, and monthly allocations so the total capital invested in every single month across all strategies is strictly equal.
  - **Custom Installments Mode**: Test custom amounts for each strategy (e.g., $25/day vs $500/month).
- **Institutional Portfolio Analytics**:
  - Total Capital Invested & Ending Portfolio Value
  - Net Absolute Profit ($ or ₹) & Total Return (%)
  - Annualized Return (CAGR)
  - Money-Weighted Rate of Return (**XIRR**) computed via SciPy optimization
  - Total Units Accumulated & **Average Cost Basis** (DCA efficiency)
  - Maximum Drawdown (%) & Volatility
- **Interactive Visualizations**:
  - Multi-line portfolio growth equity curves vs invested capital
  - Underlying stock price chart with visual buy point execution dots
  - Percentage return curves
  - Year-by-year summary breakdown table
  - Execution transaction log with one-click **CSV export**

---

## 💻 Local Quickstart

### Method 1: Using the provided launcher script (`run.sh`)

Ensure your conda environment is activated as required:

```bash
cd "trading scripts/backtester_app"
./run.sh
```

Or manually:

```bash
conda activate mt
pip install -r requirements.txt
uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser and navigate to: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🐳 Docker Deployment on Ubuntu Server (Tailscale Access)

You can easily deploy and run this containerized on your Ubuntu server and access it securely through your private Tailscale network.

### 1. Build and Run with Docker Compose

On your Ubuntu server:

```bash
# Clone or copy the backtester_app folder to your server
cd backtester_app

# Start the container in background
docker compose up -d --build
```

To view logs:
```bash
docker compose logs -f
```

To stop:
```bash
docker compose down
```

### 2. Accessing via Tailscale

1. Verify your Ubuntu server's Tailscale IP address:
   ```bash
   tailscale ip -4
   # Example output: 100.85.12.34
   ```
2. From any device connected to your Tailscale mesh (laptop, phone, tablet), open your browser and navigate to:
   ```
   http://100.85.12.34:8000
   ```
3. *(Optional) Tailscale Serve HTTPS*: If you want a secure HTTPS domain on your Tailnet without configuring certificates:
   ```bash
   tailscale serve --bg 8000
   # You can now access https://<your-server-name>.<tailnet-name>.ts.net directly!
   ```

---

## 🏗 Project Structure

```
trading scripts/backtester_app/
├── backend/
│   ├── app.py                # FastAPI server, security middleware, endpoints & static mount
│   ├── backtest_engine.py    # Calendar simulation, XIRR solver, CAGR, drawdown & analytics
│   └── data_service.py       # yfinance fetching, ticker resolution, symbol cache & search
├── frontend/
│   ├── index.html            # Single-page interface with responsive layout
│   ├── styles.css            # Dark mode glassmorphic UI tokens, badges, and animations
│   └── app.js                # Chart.js integration, state management & CSV exporter
├── Dockerfile                # Multi-stage lightweight Python container
├── docker-compose.yml        # Docker Compose configuration with restart policy
├── requirements.txt          # Python dependencies
├── run.sh                    # Launcher script activating 'mt' env
└── README.md                 # Documentation
```

---

## 🛡️ Security Features

- **Strict host binding**: By default, local script binds to `127.0.0.1`.
- **Input Sanitization**: Ticker symbols and query parameters are rigorously validated using regex patterns.
- **XSS Mitigation**: Frontend utilizes safe DOM creation methods (`textContent`, `replaceChildren`, `createElement`) avoiding raw `innerHTML` string interpolation.
- **HTTP Security Headers**: Automated CSP (`Content-Security-Policy`), `X-Frame-Options: SAMEORIGIN`, and `X-Content-Type-Options: nosniff`.
