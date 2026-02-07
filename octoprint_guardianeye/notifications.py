"""
Multi-Channel Alert Notifications for GuardianEye.

Dispatches failure alerts to:
  - OctoPrint popup (PNotify) — always on
  - Webhook (Home Assistant, IFTTT, etc.)
  - Discord (webhook with embed)
  - Telegram (Bot API with photo)
"""

import os
import logging
import requests

_logger = logging.getLogger("octoprint.plugins.guardianeye.notifications")


def send_failure_notifications(settings, reason, snapshot_path=None):
    """
    Send failure notifications to all configured channels.

    Args:
        settings: Plugin settings dict (notifications sub-dict)
        reason: Failure reason string
        snapshot_path: Path to the snapshot JPEG (for attachment, optional)
    """
    notif = settings.get("notifications", {})

    if notif.get("webhook_enabled") and notif.get("webhook_url"):
        _send_webhook(notif["webhook_url"], reason)

    if notif.get("discord_enabled") and notif.get("discord_webhook_url"):
        _send_discord(notif["discord_webhook_url"], reason, snapshot_path)

    if notif.get("telegram_enabled") and notif.get("telegram_bot_token") and notif.get("telegram_chat_id"):
        _send_telegram(notif["telegram_bot_token"], notif["telegram_chat_id"], reason, snapshot_path)


def _send_webhook(url, reason):
    """POST JSON to a webhook URL."""
    try:
        resp = requests.post(
            url,
            json={
                "event": "print_failure",
                "plugin": "guardianeye",
                "reason": reason,
            },
            timeout=10,
        )
        _logger.info("Webhook sent: %d", resp.status_code)
    except Exception as e:
        _logger.warning("Webhook failed: %s", e)


def _send_discord(webhook_url, reason, snapshot_path=None):
    """Send a Discord webhook with embed and optional snapshot."""
    try:
        embed = {
            "title": "GuardianEye — Print Failure Detected",
            "description": reason,
            "color": 0xFF0000,  # Red
        }
        payload = {"embeds": [embed]}

        if snapshot_path and os.path.exists(snapshot_path):
            with open(snapshot_path, "rb") as f:
                resp = requests.post(
                    webhook_url,
                    data={"payload_json": __import__("json").dumps(payload)},
                    files={"file": ("snapshot.jpg", f, "image/jpeg")},
                    timeout=15,
                )
        else:
            resp = requests.post(webhook_url, json=payload, timeout=10)

        _logger.info("Discord notification sent: %d", resp.status_code)
    except Exception as e:
        _logger.warning("Discord notification failed: %s", e)


def _send_telegram(bot_token, chat_id, reason, snapshot_path=None):
    """Send a Telegram message with optional photo."""
    try:
        caption = f"🚨 *GuardianEye — Print Failure*\n\n{reason}"

        if snapshot_path and os.path.exists(snapshot_path):
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            with open(snapshot_path, "rb") as f:
                resp = requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"},
                    files={"photo": ("snapshot.jpg", f, "image/jpeg")},
                    timeout=15,
                )
        else:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            resp = requests.post(
                url,
                json={"chat_id": chat_id, "text": caption, "parse_mode": "Markdown"},
                timeout=10,
            )

        _logger.info("Telegram notification sent: %d", resp.status_code)
    except Exception as e:
        _logger.warning("Telegram notification failed: %s", e)
