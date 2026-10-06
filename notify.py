"""Best-effort Discord failure alerts for headless runs.

Never raises: a broken webhook must not mask the original failure.
"""

import json
import logging
import urllib.request

import config

LOG = logging.getLogger("notify")

_MAX_CONTENT = 1900  # Discord caps message content at 2000 chars


def send_alert(title: str, details: str = "") -> bool:
    url = config.DISCORD_ALERT_WEBHOOK_URL
    if not url:
        return False
    content = f"**{title}**"
    if details:
        content += "\n```\n" + details[-(_MAX_CONTENT - len(title) - 20):] + "\n```"
    body = json.dumps({"content": content[:_MAX_CONTENT]}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json", "User-Agent": "ttspotslideshow"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            return True
    except Exception as e:
        LOG.warning("Discord alert failed: %s", e)
        return False
