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
