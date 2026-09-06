"""DataUpdateCoordinator for WaterOn (SmarterHomes)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WaterOnAPI, WaterOnAuthError, WaterOnConnectionError
from .const import DOMAIN, LOGGER


def _first_number(row: dict[str, Any], keys: tuple[str, ...]) -> float:
    """Return the first numeric value found for the given keys (0 if none)."""
    for key in keys:
        value = row.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return 0.0


def parse_apartments(raw: Any) -> list[dict[str, Any]]:
    """Normalise the apartment/meter consumption payload into a list of records."""
    apartments: list[dict[str, Any]] = []
    if not isinstance(raw, dict):
        return apartments

    rd = raw.get("response_data")
    if isinstance(rd, list):
        rows = rd
    elif isinstance(rd, dict):
        rows = rd.get("data") or rd.get("apts") or rd.get("meterReadingList") or []
    else:
        rows = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        apt_id = str(
            row.get("apartmentId")
            or row.get("apartment_id")
            or row.get("apartmentid")
            or ""
        ).strip()
        flat = (
            row.get("flatNo")
            or row.get("flat_no")
            or row.get("flat")
            or row.get("apartment_name")
            or row.get("name")
            or (apt_id or "Unknown")
        )
        consumption = _first_number(
            row, ("consumption", "totalQty", "qty", "used", "current", "reading")
        )
        apartments.append(
            {
                "id": apt_id,
                "flat": str(flat),
                "meterId": str(row.get("meterId") or row.get("meter_id") or ""),
                "consumption": consumption,
                "raw": row,
            }
        )

    return apartments


def parse_society(raw: Any) -> dict[str, Any]:
    """Extract society-wide stats from the aggregate consumption payload."""
    if not isinstance(raw, dict):
        return {}

    rd = raw.get("response_data")
    if not isinstance(rd, dict):
        return {}

    points = rd.get("data") or []
    if not isinstance(points, list):
        points = []

    quantities = [
        float(p.get("totalQty", 0) or 0)
        for p in points
        if isinstance(p, dict)
    ]

    return {
        "totalConsumption": round(sum(quantities), 2),
        "highestConsumption": round(max(quantities, default=0.0), 2),
        "lowestConsumption": round(min(quantities, default=0.0), 2),
        "dataPoints": len(quantities),
        "totalBillAmount": rd.get("totalBillAmount", 0),
        "totalCollectedAmount": rd.get("totalCollectedAmount", 0),
        "balanceAmount": rd.get("balanceAmount", 0),
        "totalPaidCount": rd.get("totalPaidCount", 0),
        "totalUnpaidCount": rd.get("totalUnpaidCount", 0),
    }


def parse_valves(raw: Any) -> list[dict[str, Any]]:
    """Normalise the valve-status payload into a list of per-meter records."""
    valves: list[dict[str, Any]] = []
    if not isinstance(raw, dict):
        return valves

    rd = raw.get("response_data")
    rows = rd.get("rows") if isinstance(rd, dict) else None
    if not isinstance(rows, list):
        return valves

    for row in rows:
        if not isinstance(row, dict):
            continue
        meter_id = str(row.get("meterId") or row.get("meter_id") or "").strip()
        if not meter_id:
            continue
        valves.append(
            {
                "meterId": meter_id,
                "aptNo": str(row.get("aptNo") or row.get("apt_no") or ""),
                "valveStatus": str(row.get("valveStatus") or "").lower(),
                "status": row.get("status"),
                "actionReason": row.get("actionReason", ""),
                "raw": row,
            }
        )
    return valves


def parse_alerts(raw: Any) -> list[dict[str, Any]]:
    """Normalise the current-alerts payload into a list of alert records."""
    alerts: list[dict[str, Any]] = []
    if not isinstance(raw, dict):
        return alerts

    rd = raw.get("response_data")
    if isinstance(rd, list):
        rows = rd
    elif isinstance(rd, dict):
        rows = rd.get("alerts") or []
    else:
        rows = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        alerts.append(
            {
                "aptNo": str(row.get("aptNo") or ""),
                "meterId": str(row.get("meterId") or row.get("meter_id") or ""),
                "alertType": row.get("alertType", ""),
                "location": str(row.get("location") or ""),
                "date": row.get("date"),
                "time": str(row.get("time") or ""),
                "quantity": row.get("quantity"),
                "raw": row,
            }
        )
    return alerts


class WaterOnDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch society and apartment water data from the WaterOn API."""

    def __init__(self, hass: HomeAssistant, api: WaterOnAPI, poll_interval: int) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self.api = api
        self.society_id = api.society_id or ""

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self._async_fetch()
        except WaterOnAuthError:
            LOGGER.info("Token expired, re-authenticating")
            await self.api.async_login()
            return await self._async_fetch()
        except WaterOnConnectionError as err:
            raise UpdateFailed(str(err)) from err

    async def _async_fetch(self) -> dict[str, Any]:
        now = datetime.now()
        month = str(now.month)
        year = str(now.year)

        society: dict[str, Any] = {}
        apartments: list[dict[str, Any]] = []
        summary: dict[str, Any] = {}
        valves: list[dict[str, Any]] = []
        alerts: list[dict[str, Any]] = []

        agg = await self.api.async_aggregate(month, year)
        if agg is not None:
            society = parse_society(agg)

        meters = await self.api.async_meters(month, year)
        if meters is not None:
            apartments = parse_apartments(meters)

        summ = await self.api.async_summary()
        if isinstance(summ, dict):
            summary = (
                summ["response_data"]
                if isinstance(summ.get("response_data"), dict)
                else summ
            )

        valve_raw = await self.api.async_valve_status()
        if valve_raw is not None:
            valves = parse_valves(valve_raw)

        alert_raw = await self.api.async_alerts("current")
        if alert_raw is not None:
            alerts = parse_alerts(alert_raw)

        return {
            "society": society,
            "apartments": apartments,
            "summary": summary,
            "valves": valves,
            "alerts": alerts,
            "month": int(month),
            "year": int(year),
            "last_update": datetime.now(timezone.utc).isoformat(),
        }

    async def async_valve_action(self, meter_id: int, action: str) -> None:
        """Send an open/close valve command and refresh state."""
        try:
            await self.api.async_valve_action(meter_id, action)
        except WaterOnAuthError:
            LOGGER.info("Token expired while toggling valve, re-authenticating")
            await self.api.async_login()
            await self.api.async_valve_action(meter_id, action)
        except WaterOnConnectionError:
            LOGGER.exception("Valve action failed")
        await self.async_request_refresh()