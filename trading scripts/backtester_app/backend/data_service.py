"""
Market Data Service for US and Indian Markets.
Fetches, normalizes, caches, and validates historical market prices using yfinance.
"""

import re
import time
import logging
from typing import Dict, Any, Optional, Tuple, List
import pandas as pd
import yfinance as yf

logger = logging.getLogger("backtester.data_service")

# Common aliases and preset mappings for user convenience
SYMBOL_MAP = {
    # Gold & Commodities
    "GOLD": "GC=F",
    "GOLD_US": "GLD",
    "GOLD_IN": "GOLDBEES.NS",
    "SILVER": "SI=F",
    "SILVER_IN": "SILVERBEES.NS",
    
    # US Indices & Major ETFs
    "SP500": "^GSPC",
    "S&P500": "^GSPC",
    "SPY": "SPY",
    "NASDAQ": "^IXIC",
    "QQQ": "QQQ",
    "DOW": "^DJI",
    
    # Indian Indices & Major ETFs
    "NIFTY": "^NSEI",
    "NIFTY50": "^NSEI",
    "NIFTY_50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
    "NIFTYBEES": "NIFTYBEES.NS",
    
    # Popular Indian stocks without suffix
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "INFY": "INFY.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "ICICIBANK": "ICICIBANK.NS",
    "ITC": "ITC.NS",
    "TATAMOTORS": "TATAMOTORS.NS",
    "SBIN": "SBIN.NS",
}

POPULAR_ASSETS = [
    {"symbol": "GC=F", "name": "Gold Futures (USD/oz)", "market": "US/Global", "category": "Commodity", "currency": "USD"},
    {"symbol": "GLD", "name": "SPDR Gold Shares ETF", "market": "US", "category": "ETF", "currency": "USD"},
    {"symbol": "GOLDBEES.NS", "name": "Nippon India Gold BeES ETF", "market": "India", "category": "ETF", "currency": "INR"},
    {"symbol": "^NSEI", "name": "Nifty 50 Index", "market": "India", "category": "Index", "currency": "INR"},
    {"symbol": "RELIANCE.NS", "name": "Reliance Industries Ltd", "market": "India", "category": "Equity", "currency": "INR"},
    {"symbol": "TCS.NS", "name": "Tata Consultancy Services", "market": "India", "category": "Equity", "currency": "INR"},
    {"symbol": "HDFCBANK.NS", "name": "HDFC Bank Ltd", "market": "India", "category": "Equity", "currency": "INR"},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "market": "US", "category": "ETF", "currency": "USD"},
    {"symbol": "QQQ", "name": "Invesco QQQ (Nasdaq 100)", "market": "US", "category": "ETF", "currency": "USD"},
    {"symbol": "AAPL", "name": "Apple Inc.", "market": "US", "category": "Equity", "currency": "USD"},
    {"symbol": "MSFT", "name": "Microsoft Corporation", "market": "US", "category": "Equity", "currency": "USD"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "market": "US", "category": "Equity", "currency": "USD"},
    {"symbol": "TSLA", "name": "Tesla Inc.", "market": "US", "category": "Equity", "currency": "USD"},
]

# Simple In-memory TTL Cache
_CACHE: Dict[str, Tuple[float, pd.DataFrame, Dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour cache


def normalize_symbol(user_input: str) -> str:
    """
    Sanitizes and normalizes ticker input for US and Indian exchanges.
    """
    clean = user_input.strip().upper()
    
    # Check predefined alias
    if clean in SYMBOL_MAP:
        return SYMBOL_MAP[clean]
    
    # Remove unwanted characters, keep valid ticker chars
    clean = re.sub(r"[^A-Z0-9^.=-]", "", clean)
    return clean


def detect_currency_and_market(symbol: str) -> Tuple[str, str]:
    """
    Detects currency ($ vs ₹) and market based on symbol suffix.
    """
    sym = symbol.upper()
    if sym.endswith(".NS") or sym.endswith(".BO") or sym in ("^NSEI", "^BSESN", "^NSEBANK"):
        return "INR", "India"
    return "USD", "US"


def fetch_historical_data(symbol: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Fetches daily adjusted price series from Yahoo Finance with caching.
    Returns (DataFrame, metadata_dict).
    """
    normalized = normalize_symbol(symbol)
    if not normalized:
        raise ValueError("Invalid ticker symbol provided.")

    cache_key = f"{normalized}_{start_date}_{end_date}"
    now = time.time()

    if cache_key in _CACHE:
        cached_time, df_cached, meta_cached = _CACHE[cache_key]
        if now - cached_time < CACHE_TTL_SECONDS:
            return df_cached.copy(), meta_cached

    try:
        ticker = yf.Ticker(normalized)
        
        kwargs = {"interval": "1d", "auto_adjust": False}
        if start_date and end_date:
            kwargs["start"] = start_date
            kwargs["end"] = end_date
        elif start_date:
            kwargs["start"] = start_date
        else:
            kwargs["period"] = "10y"

        history = ticker.history(**kwargs)

        if history.empty:
            # Fallback: if it might be an Indian stock missing .NS, try with .NS
            if not normalized.endswith(".NS") and not normalized.endswith(".BO") and not normalized.startswith("^"):
                fallback_sym = f"{normalized}.NS"
                fallback_ticker = yf.Ticker(fallback_sym)
                history = fallback_ticker.history(**kwargs)
                if not history.empty:
                    normalized = fallback_sym
                    ticker = fallback_ticker

        if history.empty:
            raise ValueError(f"No price data available for symbol '{symbol}'. Please verify the ticker.")

        # Clean dataframe
        history = history.reset_index()
        if "Date" in history.columns:
            history["Date"] = pd.to_datetime(history["Date"]).dt.tz_localize(None)
        elif "Datetime" in history.columns:
            history["Date"] = pd.to_datetime(history["Datetime"]).dt.tz_localize(None)
            history = history.drop(columns=["Datetime"])

        # Pick best price column
        if "Adj Close" in history.columns and history["Adj Close"].notna().sum() > 0:
            history["ExecutionPrice"] = history["Adj Close"]
        else:
            history["ExecutionPrice"] = history["Close"]

        # Forward fill any rare NaN close values
        history["ExecutionPrice"] = history["ExecutionPrice"].ffill().bfill()
        history["Close"] = history["Close"].ffill().bfill()
        
        history = history.sort_values("Date").reset_index(drop=True)

        currency, market = detect_currency_and_market(normalized)

        # Attempt to get company name / short info safely
        short_name = normalized
        try:
            fast_info = getattr(ticker, "fast_info", None)
            if fast_info and hasattr(fast_info, "currency") and fast_info.currency:
                if str(fast_info.currency).upper() == "INR":
                    currency = "INR"
                    market = "India"
        except Exception:
            pass

        # Match known friendly name if available
        for p in POPULAR_ASSETS:
            if p["symbol"].upper() == normalized.upper():
                short_name = p["name"]
                currency = p["currency"]
                market = p["market"]
                break

        metadata = {
            "symbol": normalized,
            "name": short_name,
            "currency": currency,
            "currencySymbol": "₹" if currency == "INR" else "$",
            "market": market,
            "startDate": history["Date"].iloc[0].strftime("%Y-%m-%d"),
            "endDate": history["Date"].iloc[-1].strftime("%Y-%m-%d"),
            "totalDays": len(history),
            "latestPrice": float(round(history["ExecutionPrice"].iloc[-1], 2)),
        }

        _CACHE[cache_key] = (now, history, metadata)
        return history.copy(), metadata

    except Exception as e:
        logger.error(f"Error fetching data for symbol {symbol}: {str(e)}")
        raise


def search_symbols(query: str) -> List[Dict[str, str]]:
    """
    Returns search suggestions for US, Indian stocks, Gold and popular indices.
    """
    q = query.strip().upper()
    if not q:
        return POPULAR_ASSETS[:8]

    matches = []
    for asset in POPULAR_ASSETS:
        if q in asset["symbol"].upper() or q in asset["name"].upper() or q in asset.get("category", "").upper():
            matches.append(asset)

    clean_sym = normalize_symbol(q)
    if clean_sym and not any(m["symbol"].upper() == clean_sym for m in matches):
        currency, market = detect_currency_and_market(clean_sym)
        matches.append({
            "symbol": clean_sym,
            "name": f"{clean_sym} ({market})",
            "market": market,
            "category": "Equity",
            "currency": currency
        })
        if not clean_sym.endswith(".NS") and not clean_sym.endswith(".BO") and not clean_sym.startswith("^"):
            matches.append({
                "symbol": f"{clean_sym}.NS",
                "name": f"{clean_sym} (NSE India)",
                "market": "India",
                "category": "Equity",
                "currency": "INR"
            })

    return matches[:10]
