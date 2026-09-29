"""
Built-in Investment Strategies for AlphaDCA.
Includes schedule-based strategies (Daily, Monthly, Weekly, Lump Sum)
and smart technical strategies (Buy The Dip, 200 SMA Booster, RSI Oversold, Value Averaging).
"""

import numpy as np
import pandas as pd
from typing import Dict, Any
from .base import BaseStrategy, Parameter
from .registry import register_strategy


# ==============================================================================
# Schedule-Based Strategies
# ==============================================================================

@register_strategy
class DailyStrategy(BaseStrategy):
    id = "daily"
    name = "Daily Investment"
    category = "Schedule"
    description = "Invests a portion of capital on every single market trading day."
    parameters = []

    def generate_orders(self, df: pd.DataFrame, config: Dict[str, Any], budget_mode: str, monthly_budget: float) -> Dict[str, float]:
        orders = {}
        month_trading_days = df.groupby("YearMonth")["Date"].count().to_dict()
        custom_amt = float(config.get("amount", 25.0))
        step_up_pct = float(config.get("step_up_pct", 0.0))
        start_year = df["Year"].iloc[0]

        for _, row in df.iterrows():
            date_str = row["Date"].strftime("%Y-%m-%d")
            ym = row["YearMonth"]
            year_idx = max(row["Year"] - start_year, 0)
            step_mult = ((1.0 + (step_up_pct / 100.0)) ** year_idx) if step_up_pct > 0 else 1.0

            if budget_mode == "normalized":
                days_in_month = month_trading_days.get(ym, 21)
                amt = (monthly_budget * step_mult) / days_in_month
            else:
                amt = custom_amt * step_mult

            orders[date_str] = round(amt, 2)
        return orders


@register_strategy
class MonthlyDayStrategy(BaseStrategy):
    id = "monthly_day"
    name = "Monthly (Configurable Day)"
    category = "Schedule"
    description = "Invests once a month on a chosen calendar day (e.g. 1st, 15th, or last day) with automatic holiday rollover."
    parameters = [
        Parameter(
            name="day_of_month",
            label="Day of Month",
            param_type="select",
            default=1,
            options=[1, 5, 10, 15, 20, 25, "last"],
            hint="Target calendar day to execute monthly order"
        )
    ]

    def generate_orders(self, df: pd.DataFrame, config: Dict[str, Any], budget_mode: str, monthly_budget: float) -> Dict[str, float]:
        orders = {}
        target_day = config.get("params", {}).get("day_of_month", 1)
        
        # Handle legacy alias parameter from frequency
        freq = config.get("frequency", "")
        if freq in ("monthly_1st", "monthly_first"):
            target_day = 1
        elif freq == "monthly_15th":
            target_day = 15
        elif freq in ("monthly_last", "monthly_end"):
            target_day = "last"

        custom_amt = float(config.get("amount", monthly_budget))
        step_up_pct = float(config.get("step_up_pct", 0.0))
        start_year = df["Year"].iloc[0]

        # Determine target execution date for each YearMonth
        if target_day == "last":
            target_dates = set(df.groupby("YearMonth")["Date"].last().dt.strftime("%Y-%m-%d"))
        else:
            try:
                day_num = int(target_day)
            except (ValueError, TypeError):
                day_num = 1
            
            # Find the first trading day on or after day_num in each month
            dates_ge = df[df["Day"] >= day_num].groupby("YearMonth")["Date"].first().dt.strftime("%Y-%m-%d").tolist()
            target_dates = set(dates_ge)

        for _, row in df.iterrows():
            date_str = row["Date"].strftime("%Y-%m-%d")
            if date_str in target_dates:
                year_idx = max(row["Year"] - start_year, 0)
                step_mult = ((1.0 + (step_up_pct / 100.0)) ** year_idx) if step_up_pct > 0 else 1.0
                amt = (monthly_budget if budget_mode == "normalized" else custom_amt) * step_mult
                orders[date_str] = round(amt, 2)

        return orders


@register_strategy
class WeeklyDayStrategy(BaseStrategy):
    id = "weekly_day"
    name = "Weekly (Configurable Weekday)"
    category = "Schedule"
    description = "Invests once every week on a chosen weekday (e.g., Every Monday)."
    parameters = [
        Parameter(
            name="day_of_week",
            label="Day of Week",
            param_type="select",
            default="Monday",
            options=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            hint="Weekday on which to execute weekly investment"
        )
    ]

    WEEKDAY_MAP = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4}

    def generate_orders(self, df: pd.DataFrame, config: Dict[str, Any], budget_mode: str, monthly_budget: float) -> Dict[str, float]:
        orders = {}
        dow_str = config.get("params", {}).get("day_of_week", "Monday")
        target_dow = self.WEEKDAY_MAP.get(dow_str, 0)

        custom_amt = float(config.get("amount", monthly_budget / 4.33))
        step_up_pct = float(config.get("step_up_pct", 0.0))
        start_year = df["Year"].iloc[0]

        prev_week = None

        for idx, row in df.iterrows():
            curr_date = row["Date"]
            date_str = curr_date.strftime("%Y-%m-%d")
            curr_week = curr_date.isocalendar()[1]
            dow = row["Weekday"]

            should_buy = False
            # Check if today is the target weekday
            if dow == target_dow:
                should_buy = True
            elif prev_week != curr_week and dow > target_dow:
                # If target day was a holiday, buy on first available day after
                should_buy = True

            if should_buy and prev_week != curr_week:
                year_idx = max(row["Year"] - start_year, 0)
                step_mult = ((1.0 + (step_up_pct / 100.0)) ** year_idx) if step_up_pct > 0 else 1.0
                amt = ((monthly_budget / 4.33) if budget_mode == "normalized" else custom_amt) * step_mult
                orders[date_str] = round(amt, 2)
                prev_week = curr_week

        return orders


@register_strategy
class BiWeeklyStrategy(BaseStrategy):
    id = "biweekly"
    name = "Bi-Weekly (Twice a Month)"
    category = "Schedule"
    description = "Invests twice every month on the 1st and 15th (or next trading days)."
    parameters = []

    def generate_orders(self, df: pd.DataFrame, config: Dict[str, Any], budget_mode: str, monthly_budget: float) -> Dict[str, float]:
        orders = {}
        first_days = set(df.groupby("YearMonth")["Date"].first().dt.strftime("%Y-%m-%d"))
        days_15 = set(df[df["Day"] >= 15].groupby("YearMonth")["Date"].first().dt.strftime("%Y-%m-%d"))
        target_dates = first_days.union(days_15)

        custom_amt = float(config.get("amount", monthly_budget / 2.0))
        step_up_pct = float(config.get("step_up_pct", 0.0))
        start_year = df["Year"].iloc[0]

        for _, row in df.iterrows():
            date_str = row["Date"].strftime("%Y-%m-%d")
            if date_str in target_dates:
                year_idx = max(row["Year"] - start_year, 0)
                step_mult = ((1.0 + (step_up_pct / 100.0)) ** year_idx) if step_up_pct > 0 else 1.0
                amt = ((monthly_budget / 2.0) if budget_mode == "normalized" else custom_amt) * step_mult
                orders[date_str] = round(amt, 2)
        return orders


@register_strategy
class LumpSumStrategy(BaseStrategy):
    id = "lump_sum"
    name = "Lump Sum (Day 1 Buy & Hold)"
    category = "Schedule"
    description = "Invests the entire equivalent capital upfront on the very first available trading day."
    parameters = []

    def generate_orders(self, df: pd.DataFrame, config: Dict[str, Any], budget_mode: str, monthly_budget: float) -> Dict[str, float]:
        orders = {}
        total_months = len(df["YearMonth"].unique())
        total_lump = (total_months * monthly_budget) if budget_mode == "normalized" else float(config.get("amount", 10000.0))
        d0_str = df["Date"].iloc[0].strftime("%Y-%m-%d")
        orders[d0_str] = round(total_lump, 2)
        return orders


# ==============================================================================
# Smart & Indicator-Based Strategies
# ==============================================================================

@register_strategy
class BuyTheDipStrategy(BaseStrategy):
    id = "buy_the_dip"
    name = "Buy The Dip (+ Monthly SIP)"
    category = "Smart & Technical"
    description = "Executes regular monthly SIP PLUS automatic bonus buying whenever the asset drops X% below its recent peak."
    parameters = [
        Parameter(
            name="dip_pct",
            label="Dip Threshold (%)",
            param_type="number",
            default=5.0,
            min_value=1.0,
            max_value=30.0,
            step=0.5,
            hint="Price drop percentage from recent peak to trigger extra buy"
        ),
        Parameter(
            name="lookback_days",
            label="Lookback Window (Days)",
            param_type="number",
            default=20,
            min_value=5,
            max_value=90,
            step=5,
            hint="Window of trading days used to calculate recent high"
        ),
        Parameter(
            name="dip_multiplier",
            label="Dip Buy Multiplier",
            param_type="number",
            default=1.5,
            min_value=0.5,
            max_value=4.0,
            step=0.25,
            hint="Multiplier of base allocation to invest on a dip"
        )
    ]

    def generate_orders(self, df: pd.DataFrame, config: Dict[str, Any], budget_mode: str, monthly_budget: float) -> Dict[str, float]:
        orders = {}
        params = config.get("params", {})
        dip_pct = float(params.get("dip_pct", 5.0))
        lookback = int(params.get("lookback_days", 20))
        dip_mult = float(params.get("dip_multiplier", 1.5))

        base_monthly = monthly_budget if budget_mode == "normalized" else float(config.get("amount", 500.0))
        step_up_pct = float(config.get("step_up_pct", 0.0))
        start_year = df["Year"].iloc[0]

        # Precompute rolling peak price (lookback window without lookahead)
        rolling_max = df["ExecutionPrice"].rolling(window=lookback, min_periods=3).max()

        first_days_of_month = set(df.groupby("YearMonth")["Date"].first().dt.strftime("%Y-%m-%d"))
        last_dip_date_idx = -999

        for idx, row in df.iterrows():
            date_str = row["Date"].strftime("%Y-%m-%d")
            price = float(row["ExecutionPrice"])
            year_idx = max(row["Year"] - start_year, 0)
            step_mult = ((1.0 + (step_up_pct / 100.0)) ** year_idx) if step_up_pct > 0 else 1.0
            order_amt = 0.0

            # 1. Monthly base contribution
            if date_str in first_days_of_month:
                order_amt += base_monthly * step_mult

            # 2. Dip condition: Price is >= dip_pct below recent rolling peak
            peak = rolling_max.iloc[idx]
            if pd.notna(peak) and peak > 0:
                drawdown_from_peak = (peak - price) / peak * 100.0
                # Trigger dip buy at most once every 5 trading days to avoid over-buying same dip
                if drawdown_from_peak >= dip_pct and (idx - last_dip_date_idx) >= 5:
                    dip_amt = (base_monthly * dip_mult * step_mult) / 2.0
                    order_amt += dip_amt
                    last_dip_date_idx = idx

            if order_amt > 0:
                orders[date_str] = round(order_amt, 2)

        return orders


@register_strategy
class SmaTrendStrategy(BaseStrategy):
    id = "sma_trend"
    name = "200-day SMA Value Booster"
    category = "Smart & Technical"
    description = "Invests monthly, but doubles the capital invested when price is below its 200-day Simple Moving Average (deep value accumulation)."
    parameters = [
        Parameter(
            name="sma_period",
            label="SMA Window (Days)",
            param_type="number",
            default=200,
            min_value=20,
            max_value=300,
            step=10,
            hint="Number of trading days for moving average"
        ),
        Parameter(
            name="boost_factor",
            label="Value Boost Multiplier",
            param_type="number",
            default=2.0,
            min_value=1.1,
            max_value=3.5,
            step=0.1,
            hint="Multiplier applied when asset price trades below SMA"
        )
    ]

    def generate_orders(self, df: pd.DataFrame, config: Dict[str, Any], budget_mode: str, monthly_budget: float) -> Dict[str, float]:
        orders = {}
        params = config.get("params", {})
        sma_period = int(params.get("sma_period", 200))
        boost_factor = float(params.get("boost_factor", 2.0))

        base_amt = monthly_budget if budget_mode == "normalized" else float(config.get("amount", 500.0))
        step_up_pct = float(config.get("step_up_pct", 0.0))
        start_year = df["Year"].iloc[0]

        sma_series = df["ExecutionPrice"].rolling(window=sma_period, min_periods=10).mean()
        first_days_of_month = set(df.groupby("YearMonth")["Date"].first().dt.strftime("%Y-%m-%d"))

        for idx, row in df.iterrows():
            date_str = row["Date"].strftime("%Y-%m-%d")
            if date_str in first_days_of_month:
                price = float(row["ExecutionPrice"])
                sma_val = sma_series.iloc[idx]
                year_idx = max(row["Year"] - start_year, 0)
                step_mult = ((1.0 + (step_up_pct / 100.0)) ** year_idx) if step_up_pct > 0 else 1.0

                # If price is below SMA, boost investment
                if pd.notna(sma_val) and price < sma_val:
                    amt = base_amt * boost_factor * step_mult
                else:
                    amt = base_amt * step_mult

                orders[date_str] = round(amt, 2)

        return orders


@register_strategy
class RsiOversoldStrategy(BaseStrategy):
    id = "rsi_oversold"
    name = "RSI Oversold Accumulator"
    category = "Smart & Technical"
    description = "Invests regular monthly amount, and boosts allocation when the 14-day RSI drops below 30 (extreme oversold sentiment)."
    parameters = [
        Parameter(
            name="rsi_threshold",
            label="RSI Threshold",
            param_type="number",
            default=30.0,
            min_value=15.0,
            max_value=45.0,
            step=1.0,
            hint="RSI level below which boost multiplier activates"
        ),
        Parameter(
            name="boost_factor",
            label="Oversold Multiplier",
            param_type="number",
            default=2.0,
            min_value=1.2,
            max_value=3.0,
            step=0.2,
            hint="Investment multiplier during oversold conditions"
        )
    ]

    def _compute_rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-9)
        return 100.0 - (100.0 / (1.0 + rs))

    def generate_orders(self, df: pd.DataFrame, config: Dict[str, Any], budget_mode: str, monthly_budget: float) -> Dict[str, float]:
        orders = {}
        params = config.get("params", {})
        rsi_thresh = float(params.get("rsi_threshold", 30.0))
        boost_factor = float(params.get("boost_factor", 2.0))

        base_amt = monthly_budget if budget_mode == "normalized" else float(config.get("amount", 500.0))
        step_up_pct = float(config.get("step_up_pct", 0.0))
        start_year = df["Year"].iloc[0]

        rsi_series = self._compute_rsi(df["ExecutionPrice"], period=14)
        first_days_of_month = set(df.groupby("YearMonth")["Date"].first().dt.strftime("%Y-%m-%d"))

        for idx, row in df.iterrows():
            date_str = row["Date"].strftime("%Y-%m-%d")
            if date_str in first_days_of_month:
                rsi_val = rsi_series.iloc[idx]
                year_idx = max(row["Year"] - start_year, 0)
                step_mult = ((1.0 + (step_up_pct / 100.0)) ** year_idx) if step_up_pct > 0 else 1.0

                if pd.notna(rsi_val) and rsi_val < rsi_thresh:
                    amt = base_amt * boost_factor * step_mult
                else:
                    amt = base_amt * step_mult

                orders[date_str] = round(amt, 2)

        return orders


@register_strategy
class ValueAveragingStrategy(BaseStrategy):
    id = "value_averaging"
    name = "Value Averaging (Dynamic Target)"
    category = "Smart & Technical"
    description = "Dynamically adjusts contribution: buys MORE when the stock drops and LESS when it rallies to maintain a steady monthly portfolio target."
    parameters = [
        Parameter(
            name="max_multiplier",
            label="Max Multiplier Cap",
            param_type="number",
            default=2.5,
            min_value=1.5,
            max_value=5.0,
            step=0.25,
            hint="Maximum periodic contribution multiplier to prevent unbounded buying"
        )
    ]

    def generate_orders(self, df: pd.DataFrame, config: Dict[str, Any], budget_mode: str, monthly_budget: float) -> Dict[str, float]:
        orders = {}
        params = config.get("params", {})
        max_mult = float(params.get("max_multiplier", 2.5))
        target_step = monthly_budget if budget_mode == "normalized" else float(config.get("amount", 500.0))

        first_days_of_month = set(df.groupby("YearMonth")["Date"].first().dt.strftime("%Y-%m-%d"))
        
        shares = 0.0
        month_count = 0

        for _, row in df.iterrows():
            date_str = row["Date"].strftime("%Y-%m-%d")
            price = float(row["ExecutionPrice"])

            if date_str in first_days_of_month and price > 0:
                month_count += 1
                target_portfolio_val = month_count * target_step
                current_portfolio_val = shares * price

                deficit = target_portfolio_val - current_portfolio_val
                # Bound between 0.25x and max_mult * target_step
                order_amt = min(max(deficit, 0.25 * target_step), max_mult * target_step)
                
                orders[date_str] = round(order_amt, 2)
                shares += order_amt / price

        return orders
