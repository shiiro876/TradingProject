# =============================================================================
# risk/position_sizer.py — Position Size Calculator
# =============================================================================
#
# PURPOSE:
#   Calculates the exact number of shares to buy for a given trade setup,
#   ensuring the trade never risks more than a defined percentage of the
#   account balance. This is the mathematical engine behind the "2% rule"
#   used by professional traders.
#
# THE 2% RULE EXPLAINED:
#   If your account is $10,000 and you risk 2% per trade, you can lose at
#   most $200 on any single trade. If your stop loss is $2.00 away from
#   your entry, you can buy 200 / 2.00 = 100 shares.
#
# FORMULA:
#   max_risk_amount = account_balance × risk_percent          (e.g., $200)
#   position_size   = max_risk_amount / (entry - stop_loss)   (e.g., 100 shares)
#   position_value  = position_size × entry_price             (e.g., $5,000)
#
# SAFETY CHECKS:
#   1. Position value must not exceed MAX_POSITION_SIZE (35%) of account
#   2. Risk per share must be positive (entry > stop_loss)
#   3. Position size is floored to whole shares (no fractional by default)
#
# KEY FUNCTIONS:
#   - calculate_position_size(account_balance, entry_price, stop_loss_price,
#                             risk_percent, allow_fractional)
#       Returns shares_to_buy, total_position_value, risk_amount.
#
# USAGE:
#   from risk.position_sizer import calculate_position_size
#   result = calculate_position_size(
#       account_balance=10000,
#       entry_price=50.00,
#       stop_loss_price=48.00,
#   )
#   print(result["shares_to_buy"])  # 100
#
# =============================================================================

import logging
import math

from config.settings import MAX_RISK_PER_TRADE, MAX_POSITION_SIZE

logger = logging.getLogger(__name__)


def calculate_position_size(
    account_balance: float,
    entry_price: float,
    stop_loss_price: float,
    risk_percent: float = MAX_RISK_PER_TRADE,
    allow_fractional: bool = False,
) -> dict:
    """
    Calculate the optimal number of shares to buy for a trade.

    Implements the percentage-risk position sizing model: determines the
    maximum number of shares that can be purchased such that if the stop
    loss is hit, the total loss does not exceed ``risk_percent`` of the
    account balance.

    Safety caps:
      - Position value capped at MAX_POSITION_SIZE (35%) of account.
      - Shares floored to whole numbers unless fractional trading is allowed.

    Args:
        account_balance:  Total account value in dollars (e.g., 10000.00).
        entry_price:      The price at which the trade will be entered.
        stop_loss_price:  The stop loss price (must be below entry for longs).
        risk_percent:     Max account percentage to risk on this trade.
                          Default: MAX_RISK_PER_TRADE (0.02 = 2%).
        allow_fractional: If True, allows fractional shares. If False (default),
                          floors to the nearest whole share.

    Returns:
        Dictionary containing:
            shares_to_buy       (int/float): Number of shares to purchase.
            total_position_value (float):    Total dollar value of the position.
            risk_amount          (float):    Maximum dollar loss if stop is hit.
            risk_per_share       (float):    Dollar distance between entry and stop.
            max_risk_allowed     (float):    Maximum risk in dollars (balance × %).
            position_pct         (float):    Position value as % of account.
            capped               (bool):     True if position was capped by max size.
            valid                (bool):     True if the calculation succeeded.
            message              (str):      Human-readable description/warning.

    Raises:
        No exceptions raised — returns valid=False with an error message
        for invalid inputs (negative balance, stop above entry, etc.).
    """
    # Input validation
    if account_balance <= 0:
        return _invalid_result("Account balance must be positive.")

    if entry_price <= 0:
        return _invalid_result("Entry price must be positive.")

    if stop_loss_price <= 0:
        return _invalid_result("Stop loss price must be positive.")

    if stop_loss_price >= entry_price:
        return _invalid_result(
            f"Stop loss (${stop_loss_price:.2f}) must be below entry "
            f"(${entry_price:.2f}) for long positions."
        )

    if not (0 < risk_percent <= 1.0):
        return _invalid_result("Risk percent must be between 0 and 1.0 (exclusive).")

    # Step 1: Calculate maximum risk in dollars
    max_risk_amount = account_balance * risk_percent

    # Step 2: Calculate risk per share (entry - stop)
    risk_per_share = entry_price - stop_loss_price

    # Step 3: Calculate raw position size
    raw_shares = max_risk_amount / risk_per_share

    # Step 4: Floor to whole shares unless fractional is allowed
    if allow_fractional:
        shares_to_buy = round(raw_shares, 4)
    else:
        shares_to_buy = math.floor(raw_shares)

    # Edge case: if flooring reduces to 0 shares
    if shares_to_buy <= 0:
        return _invalid_result(
            f"Risk budget (${max_risk_amount:.2f}) too small for risk per share "
            f"(${risk_per_share:.2f}). Cannot buy even 1 share."
        )

    # Step 5: Calculate total position value
    total_position_value = shares_to_buy * entry_price

    # Step 6: Check position size cap (35% of account)
    max_position_value = account_balance * MAX_POSITION_SIZE
    capped = False

    if total_position_value > max_position_value:
        # Reduce shares to fit within the cap
        capped = True
        if allow_fractional:
            shares_to_buy = round(max_position_value / entry_price, 4)
        else:
            shares_to_buy = math.floor(max_position_value / entry_price)

        total_position_value = shares_to_buy * entry_price
        logger.info(
            "Position capped: reduced to %s shares ($%.2f) to stay within %.0f%% limit.",
            shares_to_buy, total_position_value, MAX_POSITION_SIZE * 100,
        )

    # Step 7: Recalculate actual risk with final share count
    actual_risk = shares_to_buy * risk_per_share
    position_pct = (total_position_value / account_balance) * 100

    message = (
        f"Buy {shares_to_buy} shares @ ${entry_price:.2f} "
        f"(${total_position_value:.2f}, {position_pct:.1f}% of account). "
        f"Risk: ${actual_risk:.2f}."
    )
    if capped:
        message += " [CAPPED: position size reduced to fit 35% limit]"

    return {
        "shares_to_buy": shares_to_buy,
        "total_position_value": round(total_position_value, 2),
        "risk_amount": round(actual_risk, 2),
        "risk_per_share": round(risk_per_share, 2),
        "max_risk_allowed": round(max_risk_amount, 2),
        "position_pct": round(position_pct, 2),
        "capped": capped,
        "valid": True,
        "message": message,
    }


def _invalid_result(message: str) -> dict:
    """
    Return a standardized error result when position sizing fails.

    Ensures downstream code always receives a consistent dictionary shape,
    even when the calculation cannot proceed due to invalid inputs.

    Args:
        message: Human-readable explanation of why the calculation failed.

    Returns:
        Dictionary with valid=False and all numeric fields set to 0.
    """
    logger.warning("Position sizing failed: %s", message)
    return {
        "shares_to_buy": 0,
        "total_position_value": 0.0,
        "risk_amount": 0.0,
        "risk_per_share": 0.0,
        "max_risk_allowed": 0.0,
        "position_pct": 0.0,
        "capped": False,
        "valid": False,
        "message": message,
    }
