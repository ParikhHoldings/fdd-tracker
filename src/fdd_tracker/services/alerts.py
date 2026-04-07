from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WatchlistAlert:
    email: str
    franchise_slug: str
    summary: str


def enqueue_alert(alert: WatchlistAlert) -> None:
    """Alert dispatch stub.

    TODO: wire to Loops/Beehiiv/email provider.
    """
    _ = alert
