# bimmer_connected ⇄ EVCC BMW API Alignment Notes

Goal: adapt `bimmer_connected` so its BMW integration matches EVCC’s implementation in `vehicle/bmw` (vehicle/bmw.go:13, vehicle/bmw/provider.go:17).

## High-Level Behavior Gap
- EVCC targets synchronous Go usage with minimal dependencies, while `bimmer_connected` offers a rich async Python client. We need to pare the Python stack down to the subset EVCC actually exercises: authenticate once, fetch state via `Status`, list vehicles once, and fire remote charge controls.

## Authentication Flow
- EVCC posts fixed parameters to `/oauth/authenticate`, extracts the `authorization` query param, then exchanges it for tokens at `/oauth/token` using static credentials (vehicle/bmw/identity.go:68, vehicle/bmw/identity.go:158, vehicle/bmw/param.go:17).
- `bimmer_connected` pulls dynamic OAuth metadata (`/eadrax-ucs/v1/presentation/oauth/config`), builds PKCE verifiers, tracks hCaptcha rotation, and handles ROW/NA vs. China flows (bimmer_connected/bimmer_connected/api/authentication.py:130, bimmer_connected/bimmer_connected/api/authentication.py:165, bimmer_connected/bimmer_connected/api/authentication.py:302).
- Alignment implication: switch `bimmer_connected` to the fixed EVCC auth recipe for ROW/NA regions, bypassing the dynamic config, PKCE helpers, captcha rotation cache, and China-specific branches.

## Token Storage & Refresh
- EVCC stores the full `oauth2.Token` (with refresh token) in the EVCC settings DB and recreates a `ReuseTokenSourceWithExpiry` wrapper per session (vehicle/bmw/identity.go:48, vehicle/bmw/identity.go:182).
- `bimmer_connected` maintains async token refresh inside `MyBMWAuthentication`, offsets expiry times, persists GCID/session IDs, and exposes setters for external refresh-token injection (bimmer_connected/bimmer_connected/api/authentication.py:41, bimmer_connected/bimmer_connected/account.py:167).
- Alignment implication: implement a lightweight token cache helper that mirrors EVCC’s single-token persistence and uses refresh only on demand, without GCID/session bookkeeping.

## HTTP Client Characteristics
- EVCC wraps Go’s `http.Client` once, replacing the transport with an `oauth2.Transport` and decorating headers with a static `X-User-Agent` string (vehicle/bmw/api.go:31).
- `bimmer_connected` subclasses `httpx.AsyncClient`, injects event hooks for logging, retries, correlation IDs, and per-brand headers (bimmer_connected/bimmer_connected/api/client.py:43, bimmer_connected/bimmer_connected/api/client.py:90).
- Alignment implication: simplify `bimmer_connected` calls to a thin synchronous client (or limited async wrapper) that prepares only the `X-User-Agent` and `bmw-vin` headers EVCC needs, dropping response logging, observer-position headers, and retry hooks.

## REST Endpoints & Payloads
- EVCC hits `GET /eadrax-vcs/v4/vehicles` to enumerate VINs and `GET /eadrax-vcs/v4/vehicles/state` (with `bmw-vin` header) for telemetry, using query params `apptimezone=120` and `appDateTime=<UnixMillis>` (vehicle/bmw/api.go:45, vehicle/bmw/api.go:53).
- `bimmer_connected` prefers v5 vehicle list endpoints, enriches state with additional charging/config endpoints, and fans out per-brand requests (bimmer_connected/bimmer_connected/account.py:81, bimmer_connected/bimmer_connected/vehicle/vehicle.py:106).
- Alignment implication: constrain `bimmer_connected` to the same two endpoints and identical query/header patterns to guarantee parity with EVCC.

## Remote Services
- EVCC calls `POST eadrax-crccs/v1/vehicles/{vin}/{start|stop}-charging` for charge control and defaults other commands to the v3 VRCCS path, returning the raw event payload without polling (vehicle/bmw/api.go:90, vehicle/bmw/provider.go:121).
- `bimmer_connected` maps many services to v3/v4 VRCCS URLs, polls `/eventStatus`, and optionally refreshes vehicle data (bimmer_connected/bimmer_connected/vehicle/remote_services.py:70, bimmer_connected/bimmer_connected/vehicle/remote_services.py:153).
- Alignment implication: remove polling and additional service coverage; retain just `start-charging`, `stop-charging`, and `door-lock` with single-shot POST behavior.

## Region Coverage
- EVCC hard-codes EU and NA entries with known client IDs, states, and basic auth secrets (vehicle/bmw/param.go:17).
- `bimmer_connected` enumerates ROW, NA, CHINA (and others) via `Regions`, decoding OCP subscription keys, app versions, and user agents (bimmer_connected/bimmer_connected/api/regions.py:6, bimmer_connected/bimmer_connected/const.py:62).
- Alignment implication: collapse region handling to the EVCC map and treat unknown regions as unsupported to match EVCC’s expectations.

## Data Model Surface
- EVCC exposes only SoC, range, odometer, charging target, charger connectivity, climate activity, and basic command interfaces (vehicle/bmw/provider.go:33, vehicle/bmw/provider.go:102, vehicle/bmw/provider.go:128).
- `bimmer_connected` builds comprehensive domain models (charging profiles, tire pressure, POI uploads, etc.) to support Home Assistant integrations (bimmer_connected/bimmer_connected/vehicle/vehicle.py:153, bimmer_connected/bimmer_connected/vehicle/remote_services.py:99).
- Alignment implication: trim the vehicle model to just the EVCC-required fields and cache semantics.

## Caching Strategy
- EVCC wraps `Status` calls with `util.Cached`, controlled by the `cache` duration from configuration (vehicle/bmw/provider.go:17).
- `bimmer_connected` refreshes state on every `get_vehicle_state` invocation, optionally updating after remote services (bimmer_connected/bimmer_connected/vehicle/remote_services.py:137).
- Alignment implication: add a configurable cache layer around the state fetch to prevent rapid polling, matching EVCC’s `cache` parameter.

## Next Steps Before Coding
1. ✅ China-specific handling can be dropped; EVCC only supports EU/NA, and RoW maps directly to the EVCC “EU” settings.
2. ⚠️ Keep `bimmer_connected`’s public surface unchanged. We will rewire authentication and transport layers internally while preserving async behavior and existing entry points so it remains a drop-in replacement.
3. ❌ No extra caching to add; EVCC’s caching requirement does not translate to the Python client.

### Data Coverage Check
- EVCC consumes a narrow slice of the `/eadrax-vcs/v4/vehicles/state` payload (SoC, mileage, range, charge status, climate activity). Historical responses for that endpoint contain many additional fields that EVCC simply ignores, so the older API likely still exposes broader data. For the first iteration we should mirror exactly what EVCC reads and return sensible mock/default values for the richer properties `bimmer_connected` expects. Later iterations can probe the same endpoint (and nearby v4/v5 variants) to see if the extra structures are still available before restoring full fidelity.
