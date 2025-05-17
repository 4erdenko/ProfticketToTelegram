from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

# type: Dict[str, List[Tuple[int, int]]]
SHOW_SEAT_HISTORY: Dict[str, List[Tuple[int, int]]] = {}


def estimate_sold_out_date(show_id: str) -> Optional[datetime]:
    """Estimate sold out date using simple linear trend."""
    history = SHOW_SEAT_HISTORY.get(show_id)
    if not history or len(history) < 2:
        return None

    data = sorted(history)
    times = [t for t, _ in data]
    seats = [s for _, s in data]

    n = len(times)
    t_mean = sum(times) / n
    s_mean = sum(seats) / n
    denom = sum((t - t_mean) ** 2 for t in times)
    if not denom:
        return None

    slope = sum((t - t_mean) * (s - s_mean) for t, s in data) / denom
    if slope >= 0:
        return None

    intercept = s_mean - slope * t_mean
    estimate = -intercept / slope
    if estimate <= max(times):
        return None

    try:
        return datetime.fromtimestamp(int(estimate))
    except Exception:
        return None
