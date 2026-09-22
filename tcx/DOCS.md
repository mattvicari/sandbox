# Jandy TCX Client — Home Assistant Add-on

A Home Assistant add-on that connects to a Jandy TCX pool controller via the Zodiac cloud WebSocket API and publishes native Home Assistant sensors. Pair it with the `tcx` custom integration for real switches, lights, and numbers that supervisors can control.

Version **2026.9.1** keeps the Zodiac client token across ordinary state deltas, unwraps `main`/`pib0` payloads so water temperature is populated, and periodically requests full device state.

The add-on image is built FROM `ghcr.io/liptonj/amd64-tcx-client:native-ha-api` (the native Supervisor ha_api client). Do not rebuild from MQTT `ghcr.io/liptonj/amd64-tcx-client:latest`.

---

## Installation

1. Add this repository to Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
   `https://github.com/liptonj/hassio-addons`
2. Install the **Jandy TCX Client** add-on
3. Configure Jandy username and password
4. Start the add-on
5. Install the `tcx` custom integration (copy `custom_components/tcx` into `/config/custom_components/`) and add it with URL `http://af1e6959-tcx-client:5050`

---

## Home Assistant Entities

The add-on creates sensors on first TCX value:

| Entity ID | Type | Description |
|---|---|---|
| `sensor.tcx_pool_temperature` | Sensor | Pool water temperature (°F) |
| `sensor.tcx_air_temperature` | Sensor | Equipment enclosure air temperature (°F) |
| `sensor.tcx_swc_level` | Sensor | Salt water chlorinator output (%) |
| `sensor.tcx_light_color` | Sensor | Current pool light color |
| `binary_sensor.tcx_pump` | Binary Sensor | Pool pump/filter on or off |
| `binary_sensor.tcx_light` | Binary Sensor | Pool light on or off |
| `binary_sensor.tcx_heater` | Binary Sensor | Heater enabled |

The `tcx` integration owns the controls:

| Entity ID | Type | Description |
|---|---|---|
| `switch.tcx_pump` | Switch | Pump on/off |
| `number.tcx_pump_rpm` | Number | Pump speed |
| `light.tcx_pool_light` | Light | On/off plus 12 Jandy color programs |
| `switch.tcx_heater` | Switch | Heater enable |
| `number.tcx_heater_setpoint` | Number | Water setpoint °F |
| `number.tcx_swc_level` | Number | Chlorinator percent |

---

## REST API

Port `5050`:

### `GET /status`

Cached controller state as JSON.

### `POST /statecontrol`

```json
{
  "namespace": "filtration",
  "desired": { "pool": { "st": 1 } }
}
```

Light commands use namespace `zig` (not MQTT `zigbee`).

### `GET /tcxreconnect`

Forces a WebSocket reconnect.

---

## Migrating from MQTT

Previous versions published `pool/TCX/*` and `pool/control`. After upgrading to 2026.9.1:

1. Rebuild and start this add-on, uninstall any `tcx-client-patched` local add-on
2. Add the `tcx` integration
3. Retarget dashboards from `light.pool_light` / `switch.filter_pump` to `light.tcx_pool_light` / `switch.tcx_pump`
4. Remove the MQTT pool light, filter pump, SWC, and light-color entities
5. Remove the template that mirrored `light.pool_light` into `binary_sensor.tcx_light`
