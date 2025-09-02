from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from django.conf import settings

REMINDER_OFFSETS = getattr(settings, "LUCID_EXPIRY_REMINDER_OFFSETS", [30, 14, 7, 1])
POST_EXPIRE_INTERVAL = int(getattr(settings, "LUCID_EXPIRY_POST_INTERVAL_DAYS", 7))


@dataclass
class TriggerResult:
    kind: str  # "pre", "on", "post"
    days: int  # days_to_expiry (negative when post)


def will_trigger_on(doc, run_date: date) -> TriggerResult | None:
    """
    Returns a TriggerResult if the given document would trigger a reminder
    on run_date (date), otherwise None. Uses the fixed schedule:
      - PRE: 30/14/7/1 days before
      - ON:  expiry day (0)
      - POST: every N days after expiry (weekly by default)
    Also enforces the 'max once per day' rule via doc.last_expiry_notified_at.
    """
    if not doc.is_active or not doc.expires_at:
        return None
    # already notified earlier this run_date?
    if doc.last_expiry_notified_at and doc.last_expiry_notified_at.date() == run_date:
        return None

    expires_on = doc.expires_at.date()
    days_to_expiry = (expires_on - run_date).days

    # PRE
    if days_to_expiry in REMINDER_OFFSETS:
        return TriggerResult(kind="pre", days=days_to_expiry)

    # ON
    if days_to_expiry == 0:
        return TriggerResult(kind="on", days=0)

    # POST (weekly or configured)
    if days_to_expiry < 0:
        if not doc.last_expiry_notified_at:
            return TriggerResult(kind="post", days=days_to_expiry)
        delta_days = (run_date - doc.last_expiry_notified_at.date()).days
        if delta_days >= POST_EXPIRE_INTERVAL:
            return TriggerResult(kind="post", days=days_to_expiry)

    return None
