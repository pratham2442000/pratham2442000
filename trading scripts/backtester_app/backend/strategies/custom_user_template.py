"""
=============================================================================
  AlphaDCA - Custom User Strategy Template
=============================================================================
To add your own strategy:
1. Copy this file or create any new .py file in `backend/strategies/`.
2. Subclass `BaseStrategy`, set your `id`, `name`, and optional `parameters`.
3. Decorate with `@register_strategy`.
4. Implement `generate_orders()`. It receives the price DataFrame and returns
   a dictionary of `{"YYYY-MM-DD": amount_to_invest}`.
5. That's it! Your strategy is automatically loaded into the Web UI and API!
=============================================================================
"""

import pandas as pd
from typing import Dict, Any
from .base import BaseStrategy, Parameter
from .registry import register_strategy


@register_strategy
class ExampleCustomStrategy(BaseStrategy):
    # Unique identifier used in API and config
    id = "custom_mid_month_dip"

    # Human-friendly name displayed in the UI dropdown
    name = "Custom: Mid-Month Dip Hunter"

    # Category in the UI: "Schedule", "Smart & Technical", or "Custom"
    category = "Custom"

    # Explanation shown in UI tooltips
    description = "Invests on the 10th of every month, but if the stock had a red day (>1% drop), it invests 1.5x."

    # Configurable parameters that appear in the UI
    parameters = [
        Parameter(
            name="bonus_multiplier",
            label="Red Day Multiplier",
            param_type="number",
            default=1.5,
            min_value=1.0,
            max_value=3.0,
            step=0.1,
            hint="Multiplier applied on days following a price drop"
        )
    ]

    def generate_orders(
        self,
        df: pd.DataFrame,
        config: Dict[str, Any],
        budget_mode: str,
        monthly_budget: float
    ) -> Dict[str, float]:
        """
        Return a dictionary mapping date strings ('YYYY-MM-DD') to cash amounts to invest.
        """
        orders = {}
        bonus_mult = float(config.get("params", {}).get("bonus_multiplier", 1.5))
        base_amt = monthly_budget if budget_mode == "normalized" else float(config.get("amount", 500.0))

        # Target 10th of each month (or first trading day on/after the 10th)
        target_dates = set(df[df["Day"] >= 10].groupby("YearMonth")["Date"].first().dt.strftime("%Y-%m-%d"))

        # Daily return
        daily_returns = df["ExecutionPrice"].pct_change()

        for idx, row in df.iterrows():
            date_str = row["Date"].strftime("%Y-%m-%d")
            
            if date_str in target_dates:
                # Check if previous day was a dip
                ret = daily_returns.iloc[idx] if idx > 0 else 0
                if pd.notna(ret) and ret < -0.01:
                    amt = base_amt * bonus_mult
                else:
                    amt = base_amt
                
                orders[date_str] = round(amt, 2)

        return orders
