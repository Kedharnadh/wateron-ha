# WaterOn (SmarterHomes) for Home Assistant

Custom integration that brings your **SmarterHomes WaterOn** smart water meters into
Home Assistant. Built against the API used by the [fm.wateron.cc portal](https://fm.wateron.cc)
(unofficial, reverse-engineered). Not affiliated with SmarterHomes Technologies.

## Features

- **Society-wide sensors** — total consumption, highest/lowest day, billing amounts,
  paid/unpaid apartment counts, last update.
- **Per-apartment water consumption** sensors (litres) for every metered flat.
- **Smart valve switches** — open/close your water meter valves from HA.
- **Leakage / burst alert binary sensors** with location, start time and flow quantity.
- Everything surfaced per-apartment via the device registry (device per flat).
- Home Assistant MQTT auto-discovery is **not** required — sensors register natively.

## Installation (HACS)

1. Install [HACS](https://hacs.xyz/) if you haven't already.
2. Push this folder to a GitHub repository (e.g. `wateron-ha`).
3. HACS → *Integrations* → ⋮ menu → *Custom repositories*.
4. Add `https://github.com/your-github-user/wateron-ha` with category **Integration**.
5. Click through the added repository → **Download** → restart Home Assistant.
6. Settings → **Devices & Services** → **Add integration** → search **WaterOn**.
7. Enter the username/password you use to log in at `fm.wateron.cc`.

> **Before first install**, replace `YOUR_GITHUB` in
> `custom_components/wateron/manifest.json` with your real repository URL. Versioning is
> handled by git tags, so omit `version` from the manifest (do not add one back).

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
| Poll interval | 300 s | How often to refresh data. Minimum 60 s. |

Change it later via the integration's **Options**.

## Troubleshooting

- **`invalid_auth`** — the credentials must be the ones used on the fm.wateron.cc portal
  (often a mobile number).
- **No valves/apartments appear** — the portal ships several variants of these endpoints
  (wired vs wireless, `valve` vs `valvestate`). If entities are missing, check the Home
  Assistant logs for the "Unexpected WaterOn login error" / data errors and share one
  captured API response in an issue so the parsing can be adjusted.
- Field names in responses vary between deployments; parsing is defensive and tolerates
  the common variants (`totalQty`, `consumption`, `flatNo`, `apartmentId`, …).

## Legal

This project is an independent, unofficial integration. Use at your own risk. Do not
abuse the API — keep the poll interval ≥ 60 seconds and do not poll more than your plan
allows.