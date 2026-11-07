"""
calc/cost.py — Cost estimation for energy and water anomalies. No AI.

Tariff rules are configurable via environment variables.
Time-of-day (ToD) rates are applied for energy where timestamps are available.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from config import settings


@dataclass
class CostEstimate:
    track: str
    quantity: float          # kWh or kL
    unit: str                # 'kWh' or 'kL'
    tariff_applied: float    # ₹ per unit
    tariff_type: str         # 'flat' | 'peak' | 'off_peak'
    total_cost: float        # quantity × tariff_applied


def _parse_peak_hours(tod_str: str) -> tuple[int, int]:
    """Parse '09:00-23:00' → (9, 23)."""
    try:
        start_str, end_str = tod_str.split("-")
        start_h = int(start_str.split(":")[0])
        end_h = int(end_str.split(":")[0])
        return start_h, end_h
    except Exception:
        return 9, 23


def is_peak_hour(hour: int) -> bool:
    """Return True if the given hour (0-23) falls in the ToD peak window."""
    peak_start, peak_end = _parse_peak_hours(settings.TOD_PEAK_HOURS)
    return peak_start <= hour < peak_end


def estimate_energy_cost(
    excess_kwh: float,
    timestamp: datetime.datetime | None = None,
    use_tod: bool = True,
) -> CostEstimate:
    """
    Energy cost = excess_kwh × applicable tariff.
    If timestamp is provided and ToD is enabled, uses peak/off-peak rate.
    """
    if timestamp and use_tod:
        if is_peak_hour(timestamp.hour):
            tariff = settings.TOD_PEAK_TARIFF
            tariff_type = "peak"
        else:
            tariff = settings.ENERGY_TARIFF_PER_KWH
            tariff_type = "off_peak"
    else:
        tariff = settings.ENERGY_TARIFF_PER_KWH
        tariff_type = "flat"

    total = round(excess_kwh * tariff, 2)
    return CostEstimate(
        track="energy",
        quantity=round(excess_kwh, 3),
        unit="kWh",
        tariff_applied=tariff,
        tariff_type=tariff_type,
        total_cost=total,
    )


def estimate_water_cost(excess_kl: float) -> CostEstimate:
    """Water cost = excess_kl × ₹/kL tariff."""
    total = round(excess_kl * settings.WATER_TARIFF_PER_KL, 2)
    return CostEstimate(
        track="water",
        quantity=round(excess_kl, 3),
        unit="kL",
        tariff_applied=settings.WATER_TARIFF_PER_KL,
        tariff_type="flat",
        total_cost=total,
    )


def rank_actions_by_loss(
    actions: list[dict],
    track: str,
) -> list[dict]:
    """
    Sort actions by estimated_loss descending (highest loss = rank 1).
    Returns the same list with 'priority_rank' set.
    Pure code — no AI.
    """
    sorted_actions = sorted(
        actions,
        key=lambda a: a.get("estimated_loss", 0.0),
        reverse=True,
    )
    for rank, action in enumerate(sorted_actions, start=1):
        action["priority_rank"] = rank
    return sorted_actions

