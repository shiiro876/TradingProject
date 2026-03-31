# =============================================================================
# dashboard/charts.py — Text-Based Chart Generators
# =============================================================================
#
# PURPOSE:
#   Generates ASCII/text-based charts and visualizations for the dashboard.
#   These are lightweight, terminal-friendly representations of trading data
#   that work without any GUI or browser dependency.
#
#   Charts include:
#     - Equity curve (balance over time)
#     - P&L bar chart (monthly or per-trade)
#     - Win/loss distribution
#     - Drawdown visualization
#     - Position heatmap (by sector or symbol)
#
# KEY FUNCTIONS:
#   - render_equity_curve(equity_data)    → ASCII equity curve chart.
#   - render_pnl_bars(pnl_data)           → Horizontal bar chart of P&L.
#   - render_win_loss_chart(stats)         → Win/loss ratio visualization.
#   - render_drawdown_chart(equity_data)   → Drawdown over time.
#   - render_sector_heatmap(sector_data)   → Sector concentration display.
#   - render_sparkline(values)             → Compact inline sparkline.
#
# USAGE:
#   from dashboard.charts import render_equity_curve, render_pnl_bars
#   print(render_equity_curve(backtester.get_equity_curve()))
#   print(render_pnl_bars(journal.get_performance_stats()["monthly_pnl"]))
#
# =============================================================================

import logging

logger = logging.getLogger(__name__)

# Chart dimensions
DEFAULT_WIDTH = 60
DEFAULT_HEIGHT = 15


def render_equity_curve(
    equity_data: list[dict],
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> str:
    """
    Render an ASCII equity curve from a list of equity data points.

    Takes the equity curve from the backtester and draws a text-based
    line chart showing balance progression over time.

    Args:
        equity_data: List of dicts with "equity" key (from Backtester.get_equity_curve()).
        width:       Chart width in characters (default 60).
        height:      Chart height in rows (default 15).

    Returns:
        Multi-line string containing the ASCII chart.
    """
    if not equity_data:
        return "  [No equity data to display]"

    values = [e.get("equity", 0) for e in equity_data]
    return _render_line_chart(values, title="📈 EQUITY CURVE", width=width, height=height)


def render_pnl_bars(
    pnl_data: dict[str, float],
    width: int = DEFAULT_WIDTH,
) -> str:
    """
    Render horizontal bar chart of P&L by period (month, trade, etc.).

    Positive P&L renders bars to the right (█), negative to the left.

    Args:
        pnl_data: Dict mapping label → P&L value (e.g., {"2025-01": 150.50}).
        width:    Maximum bar width in characters.

    Returns:
        Multi-line string containing the bar chart.
    """
    if not pnl_data:
        return "  [No P&L data to display]"

    lines = []
    lines.append("")
    lines.append("  💰 P&L BY PERIOD")
    lines.append("  " + "-" * (width + 20))

    # Find max absolute value for scaling
    max_abs = max(abs(v) for v in pnl_data.values()) if pnl_data else 1
    if max_abs == 0:
        max_abs = 1

    bar_max = width // 2

    for label, value in pnl_data.items():
        bar_len = int(abs(value) / max_abs * bar_max)
        if value >= 0:
            bar = "█" * bar_len
            line = f"  {label:<12} ${value:>+10,.2f}  |{bar}"
        else:
            bar = "█" * bar_len
            padding = " " * (bar_max - bar_len)
            line = f"  {label:<12} ${value:>+10,.2f}  {padding}{bar}|"

        lines.append(line)

    lines.append("  " + "-" * (width + 20))
    return "\n".join(lines)


def render_win_loss_chart(stats: dict, width: int = 40) -> str:
    """
    Render a win/loss ratio visualization.

    Shows a horizontal bar with wins (green-ish) and losses (red-ish)
    sections, plus key statistics.

    Args:
        stats: Performance stats dict with keys: wins, losses, win_rate,
               total_trades, avg_win, avg_loss.
        width: Bar width in characters.

    Returns:
        Multi-line string containing the visualization.
    """
    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    total = stats.get("total_trades", 0)

    if total == 0:
        return "  [No trades to display]"

    win_rate = stats.get("win_rate", 0.0)

    # Build the win/loss bar
    win_chars = int(wins / total * width) if total > 0 else 0
    loss_chars = width - win_chars

    bar = "W" * win_chars + "L" * loss_chars

    lines = []
    lines.append("")
    lines.append("  🎯 WIN/LOSS DISTRIBUTION")
    lines.append("  " + "-" * (width + 20))
    lines.append(f"  [{bar}]")
    lines.append(f"  Wins: {wins}  |  Losses: {losses}  |  Win Rate: {win_rate:.1f}%")
    lines.append(f"  Avg Win: ${stats.get('avg_win', 0):+,.2f}  |  Avg Loss: ${stats.get('avg_loss', 0):+,.2f}")
    lines.append("  " + "-" * (width + 20))

    return "\n".join(lines)


def render_drawdown_chart(
    equity_data: list[dict],
    width: int = DEFAULT_WIDTH,
    height: int = 10,
) -> str:
    """
    Render an ASCII drawdown chart from equity curve data.

    Shows the drawdown (decline from peak) over time. Deeper drawdowns
    appear as taller bars below the zero line.

    Args:
        equity_data: List of dicts with "equity" key.
        width:       Chart width in characters.
        height:      Chart height in rows.

    Returns:
        Multi-line string containing the drawdown chart.
    """
    if not equity_data:
        return "  [No equity data for drawdown]"

    equities = [e.get("equity", 0) for e in equity_data]

    # Calculate drawdown at each point
    peak = equities[0]
    drawdowns = []
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = ((peak - eq) / peak * 100) if peak > 0 else 0
        drawdowns.append(dd)

    if max(drawdowns) == 0:
        return "  [No drawdown detected — all-time highs throughout]"

    return _render_bar_chart(
        drawdowns, title="📉 DRAWDOWN %", width=width, height=height, inverted=True
    )


def render_sector_heatmap(sector_data: dict[str, int]) -> str:
    """
    Render a text-based sector concentration display.

    Shows how many positions are in each sector using a simple
    horizontal bar representation.

    Args:
        sector_data: Dict mapping sector name → count of positions.

    Returns:
        Multi-line string with the sector heatmap.
    """
    if not sector_data:
        return "  [No sector data to display]"

    lines = []
    lines.append("")
    lines.append("  🏭 SECTOR CONCENTRATION")
    lines.append("  " + "-" * 50)

    max_count = max(sector_data.values()) if sector_data else 1
    if max_count == 0:
        max_count = 1

    for sector, count in sorted(sector_data.items(), key=lambda x: -x[1]):
        bar = "█" * (count * 5)
        intensity = "🔴" if count >= 2 else "🟡" if count >= 1 else "🟢"
        lines.append(f"  {intensity} {sector:<25} {count:>2} {bar}")

    lines.append("  " + "-" * 50)
    return "\n".join(lines)


def render_sparkline(values: list[float], width: int = 20) -> str:
    """
    Render a compact inline sparkline from a list of values.

    Uses Unicode block characters to create a minimal chart that fits
    in a single line — useful for inline display in tables.

    Args:
        values: List of numerical values.
        width:  Maximum sparkline width in characters.

    Returns:
        Single-line string containing the sparkline.
    """
    if not values:
        return ""

    # Subsample if too many values
    if len(values) > width:
        step = len(values) / width
        sampled = [values[int(i * step)] for i in range(width)]
    else:
        sampled = list(values)

    min_val = min(sampled)
    max_val = max(sampled)
    val_range = max_val - min_val

    if val_range == 0:
        return "▄" * len(sampled)

    # Map to block characters (8 levels)
    blocks = " ▁▂▃▄▅▆▇█"
    sparkline = ""
    for v in sampled:
        level = int((v - min_val) / val_range * 8)
        level = min(level, 8)
        sparkline += blocks[level]

    return sparkline


def render_trade_table(trades: list[dict], max_rows: int = 10) -> str:
    """
    Render a formatted table of recent trades.

    Args:
        trades:   List of trade dicts with symbol, entry_price, exit_price,
                  pnl, exit_reason, etc.
        max_rows: Maximum number of rows to display.

    Returns:
        Multi-line string containing the formatted table.
    """
    if not trades:
        return "  [No trades to display]"

    lines = []
    lines.append("")
    lines.append("  📋 RECENT TRADES")
    lines.append(
        "  " + "-" * 72
    )
    lines.append(
        f"  {'Symbol':<8} {'Entry':>8} {'Exit':>8} {'Shares':>7} "
        f"{'P&L':>10} {'Reason':<15}"
    )
    lines.append("  " + "-" * 72)

    for trade in trades[-max_rows:]:
        symbol = trade.get("symbol", "???")
        entry = trade.get("entry_price", 0)
        exit_p = trade.get("exit_price", 0)
        shares = trade.get("shares", 0)
        pnl = trade.get("pnl", trade.get("profit_loss_dollar", 0))
        reason = trade.get("exit_reason", "unknown")

        lines.append(
            f"  {symbol:<8} ${entry:>7.2f} ${exit_p:>7.2f} {shares:>7} "
            f"${pnl:>+9.2f} {reason:<15}"
        )

    lines.append("  " + "-" * 72)
    return "\n".join(lines)


# =============================================================================
# Private: Rendering Helpers
# =============================================================================

def _render_line_chart(
    values: list[float],
    title: str = "Chart",
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> str:
    """
    Render an ASCII line chart from a list of numerical values.

    Uses braille-style plotting with simple characters.
    """
    if not values:
        return "  [No data]"

    # Subsample to fit width
    if len(values) > width:
        step = len(values) / width
        sampled = [values[int(i * step)] for i in range(width)]
    else:
        sampled = list(values)

    min_val = min(sampled)
    max_val = max(sampled)
    val_range = max_val - min_val

    if val_range == 0:
        val_range = 1  # Prevent division by zero

    lines = []
    lines.append(f"\n  {title}")
    lines.append("  " + "-" * (len(sampled) + 15))

    # Build grid row by row (top to bottom)
    for row in range(height - 1, -1, -1):
        threshold = min_val + (row / (height - 1)) * val_range if height > 1 else min_val
        label = f"${threshold:>10,.0f}" if threshold >= 100 else f"${threshold:>10,.2f}"
        line = f"  {label} |"
        for val in sampled:
            if val >= threshold:
                line += "█"
            else:
                line += " "
        lines.append(line)

    # X axis
    lines.append("  " + " " * 11 + "+" + "─" * len(sampled))
    lines.append("  " + "-" * (len(sampled) + 15))

    return "\n".join(lines)


def _render_bar_chart(
    values: list[float],
    title: str = "Chart",
    width: int = DEFAULT_WIDTH,
    height: int = 10,
    inverted: bool = False,
) -> str:
    """
    Render a vertical bar chart from a list of values.

    Used primarily for drawdown visualization (inverted=True).
    """
    if not values:
        return "  [No data]"

    # Subsample to fit width
    if len(values) > width:
        step = len(values) / width
        sampled = [values[int(i * step)] for i in range(width)]
    else:
        sampled = list(values)

    max_val = max(sampled) if sampled else 1
    if max_val == 0:
        max_val = 1

    lines = []
    lines.append(f"\n  {title}")
    lines.append("  " + "-" * (len(sampled) + 10))

    for row in range(height, 0, -1):
        threshold = (row / height) * max_val
        label = f"  {threshold:>6.1f}% |" if inverted else f"  {threshold:>6.1f} |"
        line = label
        for val in sampled:
            if val >= threshold:
                line += "▓"
            else:
                line += " "
        lines.append(line)

    lines.append("  " + " " * 8 + "+" + "─" * len(sampled))
    lines.append("  " + "-" * (len(sampled) + 10))

    return "\n".join(lines)
