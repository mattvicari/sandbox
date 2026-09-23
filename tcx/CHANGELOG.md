## 2026.9.1.5

- Surface the raw `TspBdy0` heater payload as `raw_*` attributes on
  `binary_sensor.tcx_heater`, so an "actively heating" field (not yet
  identified — Zodiac's cloud API only confirms enabled/setpoint) can be
  spotted from Developer Tools → States instead of digging through logs

## 2026.9.1.4

- Fix `GET /status` returning a double-encoded JSON string instead of a JSON
  object (`Status.get()` returned `json.dumps(...)`, which flask_restful then
  encoded again), which broke the `tcx` custom integration's state updates

## 2026.9.1.3

- Surface the real HTTP status/body when Jandy login fails instead of crashing
  with a cryptic `TypeError` when the cloud API doesn't return credentials

## 2026.9.1.2

- Vendor the `jandy` package in-tree instead of depending on the unmaintained,
  amd64-only `ghcr.io/liptonj/amd64-tcx-client:native-ha-api` base image
- Build FROM `ghcr.io/home-assistant/{arch}-base-python:3.12-alpine3.20`, which
  publishes both amd64 and aarch64, so the add-on now builds natively on aarch64

## 2026.9.1

- Overlay the token-preserving native client, safe launcher, and periodic full-state refresh
- Share one CONST module between Flask `/status` and WebSocket processors
- Republish HA sensors after Core restarts instead of skipping on a stale cache
- Build FROM `ghcr.io/liptonj/amd64-tcx-client:native-ha-api` instead of the MQTT `:latest` image
- Document native HA pump, light, heater, setpoint, RPM, and SWC controls via `custom_components/tcx`

## 2026.5.40

- Native Home Assistant sensors via Supervisor API (no MQTT broker options)

## Earlier

- Added auto reconnect
- Added auto reconnect time
- DOCS updated
- Added ping timer option
