# preferences/utils.py
from __future__ import annotations

from typing import Any, List
from django.core.cache import cache

from .models import SiteSetting


def _get_cached(key: str, default: Any) -> Any:
    """
    Read SiteSetting.value['v'] with a tiny cache layer.
    """
    cache_key = f"sitesetting:{key}"
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    try:
        s = SiteSetting.objects.get(
            key=key
        )  # SiteSetting.DoesNotExist is part of the model class
        val = s.value.get("v", default)
    except SiteSetting.DoesNotExist:
        val = default

    cache.set(cache_key, val, 60)  # 1 minute cache
    return val


def get_site_setting(key: str, default: Any = None) -> Any:
    """
    Public helper to fetch a single setting's 'v' value (or default).
    """
    return _get_cached(key, default)


def get_expiry_schedule_days(default: List[int] | None = None) -> List[int]:
    """
    Returns a normalized, ascending list of reminder day offsets before expiry.
    Example: [1, 7, 14, 30]
    """
    default = default or [30, 14, 7, 1]
    raw = get_site_setting("expiry_schedule_days", default)

    if not isinstance(raw, list):
        return sorted(set(default))

    days = []
    for x in raw:
        try:
            n = int(x)
            if n >= 0:
                days.append(n)
        except Exception:
            continue
    if not days:
        return sorted(set(default))
    return sorted(set(days))
