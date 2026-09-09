# WaterOn (SmarterHomes) for Home Assistant

Custom integration that brings your **SmarterHomes WaterOn** smart water meters into
Home Assistant. Built against the APIs used by the [fm.wateron.cc portal](https://fm.wateron.cc)
and the official **WaterOn Android app** (individual flat portal)
(unofficial, reverse-engineered). Not affiliated with SmarterHomes Technologies.

## Features

- **Two account types**, chosen when adding the integration:
  - **Committee** (`fm.wateron.cc` / `api.wateron.cc`) — society-wide data.
  - **Resident** (WaterOn app / `appapi.wateron.in`) — your own flat's data, signed
    in with an OTP sent to your registered mobile number.
- **Society-wide sensors** (committee) — total consumption, highest/lowest day,
  billing amounts, paid/unpaid apartment counts, last update.
- **Per-apartment water consumption** sensors (litres) for every metered flat.
- **Historical consumption import** — on the first refresh the resident coordinator
  pulls up to 3 months of daily readings (current + previous 2 months) in a single call.
  Per-flat monthly totals are exposed as **"Consumption last month"** and
  **"Consumption 2 months ago"** sensors, and the full day-by-day readings for the
  current month are available as attributes on the water-consumption sensor
  (`daily_readings`) alongside `last_month_total` / `two_months_ago_total`.
- **Resident bill sensors** — current bill amount, bill date and paid status per flat.
- **Smart valve switches** — open/close your water meter valves from HA.
- **Leakage / burst alert binary sensors** with location, start time and flow quantity.
- **Alert history** — every past leakage/burst event is kept (up to 300 per flat). A
  diagnostic **"Alert history"** sensor counts them and exposes the full list
  (`events`) with type, timestamp, message, quantity and duration in its attributes.
- Everything surfaced per-apartment via the device registry (device per flat).
- Home Assistant MQTT auto-discovery is **not** required — sensors register natively.

## Installation (HACS)

1. Install [HACS](https://hacs.xyz/) if you haven't already.
2. Push this folder to a GitHub repository (e.g. `wateron-ha`).
3. HACS → *Integrations* → ⋮ menu → *Custom repositories*.
4. Add `https://github.com/kedharnadh/wateron-ha` with category **Integration**.
5. Click through the added repository → **Download** → restart Home Assistant.
6. Settings → **Devices & Services** → **Add integration** → search **WaterOn**.
7. Choose your account type:
   - **Committee** — the username/password you use to log in at `fm.wateron.cc`.
   - **Resident** — your country code (ISD) and mobile number. An OTP is sent to it;
     enter the OTP to finish setup.

## Development / CI

- `.github/workflows/hacs.yaml` — runs [HACS validation](https://github.com/hacs/action)
  and [hassfest](https://developers.home-assistant.io/docs/cores/internals/releasing/)
  on every push/pull request.
- `.github/workflows/release.yaml` — pushing a tag (`v0.1.0`, `v1.2.3`, …) creates a
  GitHub Release; HACS then offers the update in Home Assistant. Use
  `git push origin v0.1.0` after tagging.

## Configuration

| Setting | Default | Description |
| --- | --- | --- |
| Account type | — | `committee` or `resident` (chosen during setup). |
| Poll interval | 300 s | How often to refresh data. Minimum 60 s. |

Change the poll interval later via the integration's **Options**.

## Troubleshooting

- **`invalid_auth`** — for committee accounts the credentials must be the ones used on
  the fm.wateron.cc portal (often a mobile number). For resident accounts, an OTP is
  only sent for a mobile number registered with WaterOn.
- **`invalid_otp`** — double-check the SMS code and try again; a new OTP is re-sent if
  you go back to the mobile-number step.
- **Resident tokens expire** — the integration refreshes the auth token automatically
  using the same `/v2.0/auth/` endpoint the app uses, and persists it to the config entry.
- **No valves/apartments appear** — the portal ships several variants of these endpoints
  (wired vs wireless, `valve` vs `valvestate`). If entities are missing, check the Home
  Assistant logs and share one captured API response in an issue so the parsing can be
  adjusted.
- Field names in responses vary between deployments; parsing is defensive and tolerates
  the common variants (`totalQty`, `consumption`, `flatNo`, `apartmentId`, …).

## Legal

This project is an independent, unofficial integration. Use at your own risk. Do not
abuse the API — keep the poll interval ≥ 60 seconds and do not poll more than your plan
allows.