"""
Comprehensive Backtesting Engine for Stock, ETF, and Commodity Investment Schedules.
Calculates portfolio accumulation, mark-to-market equity curves, XIRR, CAGR,
average cost basis, max drawdown, and year-by-year performance.
"""

import datetime
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
from scipy.optimize import brentq, newton
from strategies import get_strategy


def calculate_xirr(cash_flows: List[float], dates: List[datetime.date]) -> Optional[float]:
    """
    Calculates the exact Money-Weighted Internal Rate of Return (XIRR).
    cash_flows: negative for investments, positive for final portfolio value.
    dates: corresponding datetime.date objects.
    """
    if len(cash_flows) < 2:
        return None
    
    # Must have both positive and negative flows
    if not (any(cf > 0 for cf in cash_flows) and any(cf < 0 for cf in cash_flows)):
        return None

    d0 = dates[0]
    days = np.array([(d - d0).days / 365.0 for d in dates], dtype=float)
    cfs = np.array(cash_flows, dtype=float)

    def npv(rate):
        if rate <= -0.999999:
            return float("inf")
        return float(np.sum(cfs / ((1.0 + rate) ** days)))

    try:
        # Try Newton-Raphson first with reasonable guess
        res = newton(npv, 0.1, maxiter=100, tol=1e-5)
        if -0.99 < res < 50.0:
            return round(float(res) * 100.0, 2)
    except Exception:
        pass

    try:
        # Bracket search with Brentq
        res = brentq(npv, -0.99, 10.0, maxiter=200)
        return round(float(res) * 100.0, 2)
    except Exception:
        return None


def calculate_max_drawdown(equity_curve: List[float]) -> float:
    """
    Calculates maximum portfolio drawdown percentage from peak.
    """
    if not equity_curve or len(equity_curve) < 2:
        return 0.0
    arr = np.array(equity_curve)
    peaks = np.maximum.accumulate(arr)
    # Avoid division by zero
    peaks[peaks == 0] = 1e-9
    drawdowns = (arr - peaks) / peaks
    return round(float(np.min(drawdowns)) * 100.0, 2)


def run_backtest_simulation(
    history_df: pd.DataFrame,
    strategies_config: List[Dict[str, Any]],
    budget_mode: str = "normalized",
    monthly_budget: float = 1000.0,
    lump_sum_day1: bool = False
) -> Dict[str, Any]:
    """
    Runs multi-strategy backtest simulation on historical price series.
    """
    if history_df.empty:
        raise ValueError("Price history is empty.")

    df = history_df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    df["Year"] = df["Date"].dt.year
    df["Month"] = df["Date"].dt.month
    df["Day"] = df["Date"].dt.day
    df["Weekday"] = df["Date"].dt.weekday  # 0=Monday, 4=Friday
    df["YearMonth"] = df["Date"].dt.to_period("M")

    # Map each month to its trading days count for budget normalization
    month_trading_days = df.groupby("YearMonth")["Date"].count().to_dict()
    # Map each month's first trading date
    first_trading_days_of_month = set(df.groupby("YearMonth")["Date"].first().dt.strftime("%Y-%m-%d"))
    # Map each month's 15th (or first date >= 15)
    dates_ge_15 = df[df["Day"] >= 15].groupby("YearMonth")["Date"].first().dt.strftime("%Y-%m-%d").tolist()
    trading_days_15th = set(dates_ge_15)
    # Map each month's last trading date
    last_trading_days_of_month = set(df.groupby("YearMonth")["Date"].last().dt.strftime("%Y-%m-%d"))

    total_calendar_days = (df["Date"].iloc[-1] - df["Date"].iloc[0]).days
    total_years = max(total_calendar_days / 365.25, 0.08)

    results_by_strategy = []
    
    # Track overall total budget across all months for Lump Sum normalization
    unique_months_count = len(month_trading_days)
    total_equivalent_budget = unique_months_count * monthly_budget

    for strat in strategies_config:
        strat_id = strat.get("id", "strategy")
        strat_name = strat.get("name", "Strategy")
        frequency = strat.get("frequency", "monthly_day").lower()

        # Delegate order generation to the registered strategy plugin
        try:
            strategy_handler = get_strategy(frequency)
        except KeyError:
            strategy_handler = get_strategy("daily")

        orders_map = strategy_handler.generate_orders(df, strat, budget_mode, monthly_budget)

        cash_flows: List[float] = []
        cash_flow_dates: List[datetime.date] = []
        transactions: List[Dict[str, Any]] = []

        shares_held = 0.0
        cumulative_invested = 0.0
        
        portfolio_values: List[float] = []
        invested_curve: List[float] = []
        dates_str: List[str] = []
        prices: List[float] = []

        for _, row in df.iterrows():
            current_date = row["Date"]
            date_str = current_date.strftime("%Y-%m-%d")
            price = float(row["ExecutionPrice"])

            order_amount = orders_map.get(date_str, 0.0)

            if order_amount > 0 and price > 0:
                units_bought = order_amount / price
                shares_held += units_bought
                cumulative_invested += order_amount
                d_obj = current_date.date()
                cash_flows.append(-order_amount)
                cash_flow_dates.append(d_obj)
                transactions.append({
                    "date": date_str,
                    "type": "BUY",
                    "price": round(price, 2),
                    "amount": round(order_amount, 2),
                    "shares": round(units_bought, 4),
                    "cumulativeInvested": round(cumulative_invested, 2),
                    "totalShares": round(shares_held, 4)
                })

            current_portfolio_value = shares_held * price
            portfolio_values.append(round(current_portfolio_value, 2))
            invested_curve.append(round(cumulative_invested, 2))
            dates_str.append(date_str)
            prices.append(round(price, 2))

        # Final terminal cash inflow for XIRR
        final_value = portfolio_values[-1] if portfolio_values else 0.0
        final_date = df["Date"].iloc[-1].date()
        
        # Build cashflows copy including terminal portfolio value
        terminal_cash_flows = list(cash_flows)
        terminal_dates = list(cash_flow_dates)
        if final_value > 0:
            terminal_cash_flows.append(final_value)
            terminal_dates.append(final_date)

        xirr_val = calculate_xirr(terminal_cash_flows, terminal_dates)
        max_dd = calculate_max_drawdown(portfolio_values)
        profit = final_value - cumulative_invested
        total_return_pct = round((profit / cumulative_invested * 100.0), 2) if cumulative_invested > 0 else 0.0
        
        # Annualized return (CAGR)
        if cumulative_invested > 0 and final_value > 0 and total_years > 0:
            cagr = round((((final_value / cumulative_invested) ** (1.0 / total_years)) - 1.0) * 100.0, 2)
        else:
            cagr = 0.0

        avg_cost = round(cumulative_invested / shares_held, 2) if shares_held > 0 else 0.0

        # Year by Year Breakdown Table
        df["Val_" + strat_id] = portfolio_values
        df["Inv_" + strat_id] = invested_curve
        yearly_rows = []
        for y, group in df.groupby("Year"):
            year_end_val = float(group["Val_" + strat_id].iloc[-1])
            year_end_inv = float(group["Inv_" + strat_id].iloc[-1])
            year_start_inv = float(group["Inv_" + strat_id].iloc[0])
            capital_added_year = max(year_end_inv - year_start_inv, 0.0)
            net_profit_year = year_end_val - year_end_inv
            yearly_rows.append({
                "year": int(y),
                "capitalAdded": round(capital_added_year, 2),
                "totalInvested": round(year_end_inv, 2),
                "endingValue": round(year_end_val, 2),
                "netGain": round(net_profit_year, 2),
                "gainPct": round((net_profit_year / year_end_inv * 100.0), 2) if year_end_inv > 0 else 0.0
            })

        results_by_strategy.append({
            "id": strat_id,
            "name": strat_name,
            "frequency": frequency,
            "summary": {
                "totalInvested": round(cumulative_invested, 2),
                "finalValue": round(final_value, 2),
                "netProfit": round(profit, 2),
                "totalReturnPct": total_return_pct,
                "cagr": cagr,
                "xirr": xirr_val if xirr_val is not None else cagr,
                "totalUnits": round(shares_held, 4),
                "avgCostBasis": avg_cost,
                "latestPrice": round(prices[-1], 2) if prices else 0.0,
                "maxDrawdown": max_dd,
                "totalOrders": len(transactions),
            },
            "portfolioValues": portfolio_values,
            "investedCurve": invested_curve,
            "transactions": transactions,
            "yearlyBreakdown": yearly_rows
        })

    # Downsample timeline data for smooth web rendering (up to 400 data points)
    step = max(1, len(dates_str) // 350)
    timeline_dates = dates_str[::step]
    if dates_str[-1] not in timeline_dates:
        timeline_dates.append(dates_str[-1])

    chart_series = []
    for res in results_by_strategy:
        sampled_vals = res["portfolioValues"][::step]
        sampled_inv = res["investedCurve"][::step]
        if len(sampled_vals) < len(timeline_dates):
            sampled_vals.append(res["portfolioValues"][-1])
            sampled_inv.append(res["investedCurve"][-1])
            
        chart_series.append({
            "id": res["id"],
            "name": res["name"],
            "values": sampled_vals,
            "invested": sampled_inv
        })

    timeline_prices = prices[::step]
    if len(timeline_prices) < len(timeline_dates):
        timeline_prices.append(prices[-1])

    # Determine Winner
    best_strategy = max(results_by_strategy, key=lambda s: s["summary"]["finalValue"])
    worst_strategy = min(results_by_strategy, key=lambda s: s["summary"]["finalValue"])
    diff_val = round(best_strategy["summary"]["finalValue"] - worst_strategy["summary"]["finalValue"], 2)
    diff_pct = round(best_strategy["summary"]["totalReturnPct"] - worst_strategy["summary"]["totalReturnPct"], 2)

    return {
        "dates": timeline_dates,
        "prices": timeline_prices,
        "strategies": results_by_strategy,
        "chartSeries": chart_series,
        "comparison": {
            "winnerId": best_strategy["id"],
            "winnerName": best_strategy["name"],
            "runnerUpId": worst_strategy["id"],
            "runnerUpName": worst_strategy["name"],
            "differenceValue": diff_val,
            "differencePct": diff_pct,
            "insight": f"{best_strategy['name']} generated {abs(diff_val):,.2f} more wealth ({abs(diff_pct):.2f}% higher return) than {worst_strategy['name']} over this period."
        }
    }
