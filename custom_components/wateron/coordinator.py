"""DataUpdateCoordinator for WaterOn (SmarterHomes)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WaterOnAPI, WaterOnAuthError, WaterOnConnectionError
from .api_resident import (
    WaterOnResidentAPI,
    WaterOnResidentAuthError,
    WaterOnResidentConnectionError,
)
from .const import ACCOUNT_RESIDENT, CONF_TOKEN, DOMAIN, LOGGER


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


def parse_resident_profile(raw: Any) -> list[dict[str, Any]]:
    """Normalise the /profile payload into a list of apartment records."""
    apartments: list[dict[str, Any]] = []
    if not isinstance(raw, dict):
        return apartments

    payload = raw.get("payload")
    apt_list = payload.get("apartment") if isinstance(payload, dict) else None
    if not isinstance(apt_list, list):
        return apartments

    for apt in apt_list:
        if not isinstance(apt, dict):
            continue
        try:
            apt_id = int(apt.get("aptId"))
        except (TypeError, ValueError):
            continue

        meters_raw = apt.get("meters") or []
        meters: list[dict[str, Any]] = []
        if isinstance(meters_raw, list):
            for meter in meters_raw:
                if not isinstance(meter, dict):
                    continue
                try:
                    meter_id = int(meter.get("id"))
                except (TypeError, ValueError):
                    continue
                meters.append(
                    {
                        "id": meter_id,
                        "location_default": meter.get("location_default", ""),
                        "location_user": meter.get("location_user", ""),
                        "has_valve": meter.get("has_valve") == 1,
                        "valve_current_status": meter.get("valve_current_status", ""),
                    }
                )

        commodity = apt.get("commodity")
        if not isinstance(commodity, dict):
            commodity = {}
        first_meter = meters[0]["id"] if meters else ""
        apartments.append(
            {
                "id": str(apt_id),
                "flat": str(apt.get("address") or apt_id),
                "society": apt.get("society", ""),
                "meters": meters,
                "meterId": str(first_meter),
                "unit_abbrev": commodity.get("unit_abbrev", ""),
                "currency_symbol": commodity.get("currency_symbol", ""),
                "consumption": 0.0,
            }
        )
    return apartments


def parse_resident_daily(raw: Any) -> dict[int, float]:
    """Return monthly consumption totals keyed by meter id from /getreading/daily."""
    totals: dict[int, float] = {}
    if not isinstance(raw, dict):
        return totals

    rows = raw.get("consumption") or []
    if not isinstance(rows, list):
        return totals

    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            meter_id = int(row.get("meterId"))
        except (TypeError, ValueError):
            continue
        try:
            value = float(row.get("value") or 0)
        except (TypeError, ValueError):
            value = 0.0
        totals[meter_id] = totals.get(meter_id, 0.0) + value
    return totals


def parse_resident_dashboard(raw: Any) -> dict[str, Any]:
    """Normalise the /dashboard/confinedwithinvoice response for an apartment."""
    if not isinstance(raw, dict):
        return {}
    bill = raw.get("bill")
    if not isinstance(bill, dict):
        bill = {}
    return {
        "amount": bill.get("amount"),
        "billCycleId": bill.get("billCycleId"),
        "date": bill.get("date"),
        "paid": bill.get("paid"),
        "onlineBill": raw.get("onlineBill"),
        "blockApp": raw.get("blockApp"),
        "clientId": raw.get("clientId"),
    }


def parse_resident_valve(
    raw: Any, meter_id: int | str, apt_no: str
) -> dict[str, Any]:
    """Normalise a single-meter valve status response."""
    if not isinstance(raw, dict):
        return {
            "meterId": str(meter_id),
            "aptNo": apt_no,
            "valveStatus": "",
            "status": None,
            "actionReason": "",
        }
    status = raw.get("status")
    action = raw.get("action")
    valve_status = action if isinstance(action, str) and action else status
    return {
        "meterId": str(meter_id),
        "aptNo": apt_no,
        "valveStatus": str(valve_status or "").lower(),
        "status": status,
        "action": action,
        "time": raw.get("time"),
        "actionReason": raw.get("performed_by", ""),
        "raw": raw,
    }


def parse_resident_alert(
    item: Any, apt_id: int | str, apt_no: str
) -> dict[str, Any]:
    """Normalise a single active-alert entry (no alert type is provided)."""
    meter_id = ""
    if isinstance(item, dict):
        meter = item.get("meter")
        if isinstance(meter, dict):
            meter_id = str(meter.get("id") or "")
    time = item.get("time", "") if isinstance(item, dict) else ""
    date_str, time_str = "", time
    if isinstance(time, str) and len(time) >= 10:
        date_str = time[:10]
        time_str = time[11:16] if len(time) > 11 else time
    return {
        "aptNo": apt_no,
        "meterId": meter_id,
        "alertType": "",
        "location": apt_no,
        "date": date_str,
        "time": time_str,
        "quantity": item.get("quantity") if isinstance(item, dict) else None,
        "raw": item,
    }


class WaterOnResidentDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch individual-flat water data from the WaterOn resident API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: WaterOnResidentAPI,
        entry: ConfigEntry,
        poll_interval: int,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_resident",
            update_interval=timedelta(seconds=poll_interval),
        )
        self.api = api
        self.entry = entry
        self.society_id = f"{api.isd}{api.mobile}"

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            try:
                return await self._async_fetch()
            except WaterOnResidentAuthError:
                LOGGER.info("Token expired, refreshing token")
                await self._async_refresh_token()
                return await self._async_fetch()
        except WaterOnResidentConnectionError as err:
            raise UpdateFailed(str(err)) from err

    async def _async_refresh_token(self) -> None:
        try:
            if not await self.api.async_refresh_token():
                raise WaterOnResidentAuthError("Could not refresh token")
        except WaterOnResidentAuthError as err:
            raise UpdateFailed(str(err)) from err
        await self._persist_token()

    async def _persist_token(self) -> None:
        if not self.api.token:
            return
        data = {**self.entry.data, CONF_TOKEN: self.api.token}
        self.hass.config_entries.async_update_entry(self.entry, data=data)

    async def _async_fetch(self) -> dict[str, Any]:
        now = datetime.now()
        month = str(now.month)
        year = str(now.year)
        fdate = now.replace(day=1).date().isoformat()
        tdate = now.date().isoformat()

        apartments = parse_resident_profile(await self.api.async_profile())

        meter_apt: dict[int, str] = {}
        all_meter_ids: list[int] = []
        for apt in apartments:
            for meter in apt["meters"]:
                all_meter_ids.append(meter["id"])
                meter_apt[meter["id"]] = apt["id"]

        consumption: dict[int, float] = {}
        if all_meter_ids:
            daily = await self.api.async_daily(all_meter_ids, fdate, tdate)
            consumption = parse_resident_daily(daily)
            for apt in apartments:
                apt["consumption"] = round(
                    sum(consumption.get(m["id"], 0) for m in apt["meters"]), 2
                )

        bills: dict[str, dict[str, Any]] = {}
        alerts: list[dict[str, Any]] = []
        for apt in apartments:
            apt_id = apt["id"]
            dash = await self.api.async_dashboard(apt_id)
            if dash is not None:
                bills[apt_id] = parse_resident_dashboard(dash)

            active = await self.api.async_active_alerts(apt_id)
            if isinstance(active, list):
                for item in active:
                    alerts.append(parse_resident_alert(item, apt_id, apt["flat"]))

        valves: list[dict[str, Any]] = []
        for apt in apartments:
            for meter in apt["meters"]:
                if not meter["has_valve"]:
                    continue
                status_raw = await self.api.async_valve_status(meter["id"])
                if status_raw is not None:
                    valves.append(
                        parse_resident_valve(status_raw, meter["id"], apt["flat"])
                    )

        return {
            "account_type": ACCOUNT_RESIDENT,
            "society": {},
            "apartments": apartments,
            "summary": {},
            "valves": valves,
            "alerts": alerts,
            "bills": bills,
            "daily": consumption,
            "month": int(month),
            "year": int(year),
            "last_update": datetime.now(timezone.utc).isoformat(),
        }

    async def async_valve_action(self, meter_id: int, action: str) -> None:
        """Send an open/close valve command and refresh state."""
        try:
            await self.api.async_valve_action(meter_id, action)
        except WaterOnResidentAuthError:
            LOGGER.info("Token expired while toggling valve, refreshing")
            await self._async_refresh_token()
            await self.api.async_valve_action(meter_id, action)
        except WaterOnResidentConnectionError:
            LOGGER.exception("Valve action failed")
        await self.async_request_refresh()