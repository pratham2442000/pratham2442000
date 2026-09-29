import os
import sys

# Ensure backend directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re
import logging
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware

from data_service import fetch_historical_data, search_symbols, normalize_symbol, POPULAR_ASSETS
from backtest_engine import run_backtest_simulation

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("backtester.app")

app = FastAPI(
    title="Multi-Market Investment Backtester",
    description="Backtest investment schedules (Daily vs 1st of Month vs Weekly vs Lump Sum) on US and Indian markets.",
    version="1.0.0"
)

# Security Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self';"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Enable CORS for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


from strategies import list_strategies

# Input Validation Schemas
class StrategyInput(BaseModel):
    id: str = Field(..., max_length=50)
    name: str = Field(..., max_length=100)
    frequency: str = Field(..., max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    amount: float = Field(default=100.0, ge=0.01, le=100000000.0)
    step_up_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    params: Optional[Dict[str, Any]] = Field(default_factory=dict)


class BacktestRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=25)
    startDate: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$|^$")
    endDate: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$|^$")
    budgetMode: str = Field(default="normalized", pattern="^(normalized|custom)$")
    monthlyBudget: float = Field(default=1000.0, ge=1.0, le=100000000.0)
    strategies: List[StrategyInput] = Field(..., min_length=1, max_length=5)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        clean = v.strip().upper()
        if not re.match(r"^[A-Z0-9^.=-]{1,25}$", clean):
            raise ValueError("Symbol contains invalid characters. Use letters, numbers, and standard ticker symbols.")
        return clean


@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "Multi-Market Investment Backtester", "version": "1.1.0"}


@app.get("/api/strategies")
def get_strategies():
    """
    Returns all registered strategies (schedule and technical) and their configurable parameters.
    """
    return list_strategies()


@app.get("/api/presets")
def get_presets():
    """
    Returns high-value preconfigured backtest comparisons.
    """
    return [
        {
            "id": "gold_daily_vs_monthly",
            "title": "Gold: Daily vs 1st of Month",
            "symbol": "GC=F",
            "name": "Gold Futures (USD/oz)",
            "monthlyBudget": 500,
            "period": "5y",
            "strategies": [
                {"id": "daily", "name": "Daily Investment", "frequency": "daily", "amount": 25, "step_up_pct": 0, "params": {}},
                {"id": "monthly_1st", "name": "Every 1st of Month", "frequency": "monthly_day", "amount": 500, "step_up_pct": 0, "params": {"day_of_month": 1}}
            ]
        },
        {
            "id": "gold_dip_vs_monthly",
            "title": "Gold: 1st of Month vs Buy The Dip",
            "symbol": "GC=F",
            "name": "Gold Futures (USD/oz)",
            "monthlyBudget": 500,
            "period": "5y",
            "strategies": [
                {"id": "monthly_1st", "name": "1st of Month", "frequency": "monthly_day", "amount": 500, "step_up_pct": 0, "params": {"day_of_month": 1}},
                {"id": "dip_buyer", "name": "Buy The Dip (-5%)", "frequency": "buy_the_dip", "amount": 500, "step_up_pct": 0, "params": {"dip_pct": 5.0, "lookback_days": 20, "dip_multiplier": 1.5}}
            ]
        },
        {
            "id": "gold_in_daily_vs_monthly",
            "title": "Gold India: Daily vs Monthly",
            "symbol": "GOLDBEES.NS",
            "name": "Nippon India Gold BeES ETF",
            "monthlyBudget": 10000,
            "period": "5y",
            "strategies": [
                {"id": "daily", "name": "Daily Investment", "frequency": "daily", "amount": 500, "step_up_pct": 0, "params": {}},
                {"id": "monthly_1st", "name": "Every 1st of Month", "frequency": "monthly_day", "amount": 10000, "step_up_pct": 0, "params": {"day_of_month": 1}}
            ]
        },
        {
            "id": "nifty_daily_vs_monthly",
            "title": "Nifty 50: Daily vs 1st of Month",
            "symbol": "^NSEI",
            "name": "Nifty 50 Index (India)",
            "monthlyBudget": 15000,
            "period": "10y",
            "strategies": [
                {"id": "daily", "name": "Daily SIP", "frequency": "daily", "amount": 750, "step_up_pct": 0, "params": {}},
                {"id": "monthly_1st", "name": "1st of Month SIP", "frequency": "monthly_day", "amount": 15000, "step_up_pct": 0, "params": {"day_of_month": 1}},
                {"id": "dip_buyer", "name": "Dip Accumulator", "frequency": "buy_the_dip", "amount": 15000, "step_up_pct": 0, "params": {"dip_pct": 4.0, "lookback_days": 20, "dip_multiplier": 2.0}}
            ]
        },
        {
            "id": "sp500_dca_vs_sma",
            "title": "S&P 500: Monthly vs 200 SMA Booster",
            "symbol": "SPY",
            "name": "SPDR S&P 500 ETF Trust",
            "monthlyBudget": 1000,
            "period": "10y",
            "strategies": [
                {"id": "monthly_1st", "name": "Monthly DCA (1st)", "frequency": "monthly_day", "amount": 1000, "step_up_pct": 0, "params": {"day_of_month": 1}},
                {"id": "sma_boost", "name": "200 SMA Value Booster", "frequency": "sma_trend", "amount": 1000, "step_up_pct": 0, "params": {"sma_period": 200, "boost_factor": 2.0}}
            ]
        },
        {
            "id": "apple_weekly_vs_monthly",
            "title": "Apple: Weekly vs Monthly (1st)",
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "monthlyBudget": 800,
            "period": "5y",
            "strategies": [
                {"id": "weekly", "name": "Every Monday", "frequency": "weekly_day", "amount": 200, "step_up_pct": 0, "params": {"day_of_week": "Monday"}},
                {"id": "monthly_1st", "name": "1st of Month", "frequency": "monthly_day", "amount": 800, "step_up_pct": 0, "params": {"day_of_month": 1}}
            ]
        }
    ]


@app.get("/api/search")
def search(q: str = ""):
    """
    Autocomplete search for symbols across US, India, and commodities.
    """
    return search_symbols(q)


@app.post("/api/backtest")
def run_backtest(req: BacktestRequest):
    """
    Executes backtest calculation across specified strategies.
    """
    try:
        start = req.startDate if req.startDate else None
        end = req.endDate if req.endDate else None

        df, metadata = fetch_historical_data(req.symbol, start_date=start, end_date=end)
        
        simulation_result = run_backtest_simulation(
            history_df=df,
            strategies_config=[s.dict() for s in req.strategies],
            budget_mode=req.budgetMode,
            monthly_budget=req.monthlyBudget
        )

        return {
            "success": True,
            "metadata": metadata,
            "result": simulation_result
        }
    except ValueError as ve:
        logger.warning(f"Validation/Data error in backtest: {str(ve)}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Unexpected error in backtest: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Simulation error: {str(e)}")


# Mount Static Frontend
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    def serve_frontend_root():
        return FileResponse(os.path.join(frontend_dir, "index.html"))

    @app.get("/{full_path:path}")
    def serve_frontend_files(full_path: str):
        file_path = os.path.join(frontend_dir, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dir, "index.html"))
