# =============================================================================
# dashboard/alerts.py — Alert & Notification Manager
# =============================================================================
#
# PURPOSE:
#   Manages alerts and notifications for the trading system. Alerts are
#   generated when important events occur (trade fills, stop hits, drawdown
#   warnings, system errors) and can be delivered via multiple channels:
#
#     1. Console alerts — always available (logged to history + printed)
#     2. Telegram notifications — sent via Telegram Bot API when configured
#
#   The alert system supports three severity levels:
#     - INFO:     Routine events (trade filled, position opened)
#     - WARNING:  Needs attention (approaching drawdown limit, daily loss)
#     - CRITICAL: Requires immediate action (trading halted, system error)
#
# KEY FUNCTIONS:
#   - AlertManager(telegram_token, telegram_chat_id)
#       Manages alert creation, storage, and delivery.
#
#   - send_alert(message, level)     → Create and deliver an alert.
#   - alert_trade_fill(symbol, ...)  → Alert for completed trade fill.
#   - alert_position_exit(symbol, ...)→ Alert for position exit.
#   - alert_drawdown_warning(pct)    → Alert for drawdown threshold breach.
#   - alert_trading_halted(reason)   → Critical alert for trading halt.
#   - get_alert_history(limit)       → Get recent alerts.
#   - get_alert_summary()            → Count alerts by level.
#
# USAGE:
#   from dashboard.alerts import AlertManager
#   alerts = AlertManager()
#   alerts.send_alert("AAPL bought: 33 shares @ $150.00", level="INFO")
#   alerts.alert_drawdown_warning(12.5)
#
# =============================================================================

import logging
from datetime import datetime

import requests

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


class AlertManager:
    """
    Manages alerts and notifications across multiple delivery channels.

    Stores alert history in memory and optionally sends Telegram messages
    when credentials are configured. All alerts are always logged to the
    Python logger regardless of delivery channel.

    Attributes:
        telegram_token   (str):  Telegram Bot API token.
        telegram_chat_id (str):  Telegram chat/channel ID for messages.
        alert_history    (list): In-memory log of all alerts.
        telegram_enabled (bool): Whether Telegram delivery is active.
    """

    def __init__(
        self,
        telegram_token: str | None = None,
        telegram_chat_id: str | None = None,
    ):
        """
        Initialize the alert manager.

        Args:
            telegram_token:   Telegram Bot API token. Defaults to config value.
            telegram_chat_id: Telegram chat ID. Defaults to config value.
        """
        self.telegram_token = telegram_token or TELEGRAM_BOT_TOKEN
        self.telegram_chat_id = telegram_chat_id or TELEGRAM_CHAT_ID
        self.telegram_enabled = bool(self.telegram_token and self.telegram_chat_id)
        self.alert_history: list[dict] = []

        if self.telegram_enabled:
            logger.info("AlertManager initialized with Telegram notifications enabled.")
        else:
            logger.info("AlertManager initialized (Telegram disabled — no credentials).")

    def send_alert(self, message: str, level: str = "INFO") -> dict:
        """
        Create and deliver an alert through all active channels.

        The alert is:
          1. Added to the in-memory alert history.
          2. Logged via the Python logger.
          3. Sent to Telegram (if configured).

        Args:
            message: Human-readable alert message.
            level:   Severity level: "INFO", "WARNING", or "CRITICAL".

        Returns:
            Alert record dict with timestamp, level, message, and delivery status.
        """
        level = level.upper()
        if level not in ("INFO", "WARNING", "CRITICAL"):
            level = "INFO"

        alert = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": level,
            "message": message,
            "telegram_sent": False,
        }

        # Log via Python logger
        if level == "CRITICAL":
            logger.critical("🔴 ALERT: %s", message)
        elif level == "WARNING":
            logger.warning("🟡 ALERT: %s", message)
        else:
            logger.info("🟢 ALERT: %s", message)

        # Send to Telegram if available
        if self.telegram_enabled:
            success = self._send_telegram(message, level)
            alert["telegram_sent"] = success

        # Store in history
        self.alert_history.append(alert)

        return alert

    def alert_trade_fill(
        self,
        symbol: str,
        side: str,
        shares: int | float,
        price: float,
    ) -> dict:
        """
        Send an alert for a completed trade fill.

        Args:
            symbol: Stock ticker.
            side:   "buy" or "sell".
            shares: Number of shares.
            price:  Fill price.

        Returns:
            Alert record dict.
        """
        side_upper = side.upper()
        emoji = "🟢" if side_upper == "BUY" else "🔴"
        message = (
            f"{emoji} {side_upper}: {symbol} — {shares} shares @ ${price:.2f}"
        )
        return self.send_alert(message, level="INFO")

    def alert_position_exit(
        self,
        symbol: str,
        reason: str,
        pnl: float,
        exit_price: float,
    ) -> dict:
        """
        Send an alert for a position exit.

        Args:
            symbol:     Stock ticker.
            reason:     Exit reason (e.g., "trailing_stop", "tp1", "tp2").
            pnl:        Realized P&L in dollars.
            exit_price: Price at which the position was closed.

        Returns:
            Alert record dict.
        """
        emoji = "✅" if pnl > 0 else "❌"
        message = (
            f"{emoji} EXIT {symbol}: {reason} @ ${exit_price:.2f} "
            f"(P&L: ${pnl:+,.2f})"
        )
        level = "INFO" if pnl > 0 else "WARNING"
        return self.send_alert(message, level=level)

    def alert_drawdown_warning(self, drawdown_pct: float) -> dict:
        """
        Send an alert when drawdown approaches the limit.

        Args:
            drawdown_pct: Current drawdown percentage (e.g., 12.5 for 12.5%).

        Returns:
            Alert record dict.
        """
        if drawdown_pct >= 15.0:
            message = (
                f"⛔ CRITICAL: Drawdown at {drawdown_pct:.1f}% — "
                f"TRADING HALTED. Manual review required."
            )
            return self.send_alert(message, level="CRITICAL")
        elif drawdown_pct >= 10.0:
            message = (
                f"⚠️ WARNING: Drawdown at {drawdown_pct:.1f}% — "
                f"approaching 15% halt threshold."
            )
            return self.send_alert(message, level="WARNING")
        else:
            message = f"📊 Drawdown update: {drawdown_pct:.1f}%"
            return self.send_alert(message, level="INFO")

    def alert_trading_halted(self, reason: str) -> dict:
        """
        Send a critical alert when trading is halted.

        Args:
            reason: Why trading was halted (e.g., "Max drawdown exceeded").

        Returns:
            Alert record dict.
        """
        message = f"⛔ TRADING HALTED: {reason}"
        return self.send_alert(message, level="CRITICAL")

    def alert_daily_loss_limit(self, daily_loss_pct: float) -> dict:
        """
        Send an alert when the daily loss limit is approached or breached.

        Args:
            daily_loss_pct: Current daily loss percentage.

        Returns:
            Alert record dict.
        """
        message = (
            f"⚠️ Daily loss at {daily_loss_pct:.1f}% — "
            f"approaching daily limit."
        )
        level = "CRITICAL" if daily_loss_pct >= 5.0 else "WARNING"
        return self.send_alert(message, level=level)

    def alert_system_error(self, error_message: str) -> dict:
        """
        Send a critical alert for a system error.

        Args:
            error_message: Description of the error.

        Returns:
            Alert record dict.
        """
        message = f"🚨 SYSTEM ERROR: {error_message}"
        return self.send_alert(message, level="CRITICAL")

    def get_alert_history(self, limit: int = 50) -> list[dict]:
        """
        Get the most recent alerts from history.

        Args:
            limit: Maximum number of alerts to return.

        Returns:
            List of alert dicts (newest first).
        """
        return list(reversed(self.alert_history[-limit:]))

    def get_alert_summary(self) -> dict:
        """
        Get a summary of alert counts by severity level.

        Returns:
            Dictionary with counts: info, warning, critical, total.
        """
        info_count = sum(1 for a in self.alert_history if a["level"] == "INFO")
        warn_count = sum(1 for a in self.alert_history if a["level"] == "WARNING")
        crit_count = sum(1 for a in self.alert_history if a["level"] == "CRITICAL")

        return {
            "total": len(self.alert_history),
            "info": info_count,
            "warning": warn_count,
            "critical": crit_count,
        }

    def clear_history(self) -> int:
        """
        Clear the alert history.

        Returns:
            Number of alerts that were cleared.
        """
        count = len(self.alert_history)
        self.alert_history.clear()
        return count

    def print_alert_summary(self) -> None:
        """
        Print a formatted alert summary to the console.
        """
        summary = self.get_alert_summary()

        print("\n" + "=" * 50)
        print("  🔔 ALERT SUMMARY")
        print("=" * 50)
        print(f"  Total Alerts:    {summary['total']}")
        print(f"  🟢 Info:         {summary['info']}")
        print(f"  🟡 Warning:      {summary['warning']}")
        print(f"  🔴 Critical:     {summary['critical']}")
        print("-" * 50)

        # Show last 5 alerts
        recent = self.get_alert_history(limit=5)
        if recent:
            print("  Recent:")
            for alert in recent:
                icon = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🟢"}.get(
                    alert["level"], "⚪"
                )
                print(f"    {icon} [{alert['timestamp']}] {alert['message']}")

        print("=" * 50 + "\n")

    # =========================================================================
    # Private: Telegram Integration
    # =========================================================================

    def _send_telegram(self, message: str, level: str) -> bool:
        """
        Send a message via the Telegram Bot API.

        Args:
            message: Text message to send.
            level:   Alert level (for emoji prefix).

        Returns:
            True if the message was sent successfully, False otherwise.
        """
        if not self.telegram_enabled:
            return False

        # Add emoji prefix based on level
        prefix = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🟢"}.get(level, "")
        full_message = f"{prefix} TradingBot: {message}"

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": full_message,
            "parse_mode": "HTML",
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("Telegram alert sent successfully.")
                return True
            else:
                logger.warning(
                    "Telegram API returned status %d: %s",
                    response.status_code, response.text,
                )
                return False
        except requests.RequestException as exc:
            logger.error("Failed to send Telegram alert: %s", exc)
            return False
