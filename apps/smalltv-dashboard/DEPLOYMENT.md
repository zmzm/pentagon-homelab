# Deployment — 2026-10-26

Installed smalltv-mod v3.1.0, standard ESP8266 image, on SmallTV-Ultra previously
running Ultra-V9.0.40. Both uploads returned HTTP 200 Update Success. Installation
used Raspberry Pi Ethernet for normal access and its previously unused wlan0 for
the loader/setup access points. Temporary NetworkManager profiles were removed.

Device: http://192.168.0.106/ — hostname `homelab-smalltv`.
Selected mode: `theme`; theme ID: `pentagon-homelab`; brightness: 60.
The device accepted the 1,451-byte theme package (HTTP 201), selected it (HTTP
200), and listed it as valid with no error. Its API confirms v3.1.0 and a live
station connection on the home network.

The stock API returned a masked Wi-Fi password. That mask was initially copied
as configuration; nonetheless the ESP8266 subsequently rejoined the original
home network. The exact source of the working credential was not inspected;
retained SDK Wi-Fi state is a possibility. Password portability after clearing
SDK state or a factory reset is unverified. Enter the real Wi-Fi password in
the device settings when changing networks or preparing a portable backup.
No Wi-Fi secrets are included in these deliverables.

JSON backend: http://192.168.0.185:8096/screen.json
Source: `/home/pentagon-admin/Documents/homelab/apps/smalltv-dashboard`.
Compose project: `smalltv-dashboard`; container health: healthy.
The service has restart-unless-stopped and a read-only filesystem; no Docker
socket or service credentials are mounted. The host kernel does not enforce
the configured container memory limit; Docker reported that limitation.

Verification:

- Six Python behavior tests passed.
- Official v3.1.0 theme packer and actual C++ validator accepted the package.
- Downloaded firmware SHA-256 values matched the release asset digests.
- Both live pages returned real metrics, including host CPU temperature, RAM,
  load, root filesystem space and Pi-hole statistics.
- A capture filtered to device traffic on port 8096 observed repeated
  `GET /screen.json` requests with `ESP8266HTTPClient` user agent.
- The user confirmed that different server screens are visible on the device.

The initial two pages rotate every twenty seconds. This is page content in one
JSON-fed theme, rather than multiple separately installed theme packages.
Backups, container health and Matrix integration are not implemented in this
first version. Clock timezone was set for Warsaw; the feed timestamp remains
explicit UTC. Offline firmware keeps its last values and timestamp.

## Modern design update — 2026-10-26

Active theme changed to `pentagon-modern` version 2.0.0. It polls the additive
`/screen-v2.json` endpoint with eight compact fields. The original endpoint and
theme remain available. The 2,350-byte new theme uses thirteen native text/shape
layers, with a large primary value, rounded metric cards, mint proportional
indicator and an amber unavailable/stale badge. It contains no bitmap assets.

All eight backend tests pass, and the firmware's official C++ validator accepts
the final package. Preview PNG/HTML files show the actual firmware renderer.
The rebuilt backend returns healthy status and both JSON contracts over HTTP.
Uploading beside the running original theme reset the device; switching to
stocks mode first freed memory, after which upload returned HTTP 201 and
selection returned HTTP 200. This procedure should be used for theme updates
on this ESP8266. The original theme remains installed for rollback.

## Bialystok clock and weather — 2026-10-26

Added Open-Meteo current conditions for the geocoded Polish city at 53.13333,
23.16433. An independent worker polls every 600 seconds and retries errors
after sixty seconds, keeping weather latency out of the existing host checks.
The response validates numeric fields, WMO codes and observation timestamps.
Missing, stale and expired weather are explicitly distinguished.

Active theme: `bialystok-clock-v2` (version 1.1.0, fourteen native layers,
2,941 bytes). It displays a large local clock, date, and a lower card with
weather icon, thermometer, rounded Celsius temperature and a short condition.
The clock stays visible while weather/host/DNS cards rotate 40/20/20 seconds.
All components are native text/shapes driven by eight JSON fields; there are
no raster assets. Clock tokens run locally between JSON updates.

The initial twenty-layer variant exhausted memory and was replaced with the
fourteen-layer variant. Earlier server themes remain installed for rollback.
Clock settings were corrected to use separate IANA display name and POSIX TZ
rule; device status confirmed `Europe/Warsaw` and correct local time.

Twelve backend tests passed, including weather input validation, stale/expired
data, day/night/rain/snow mapping and preservation of both server cards. The
official native firmware validator accepted the final package. Device upload
returned HTTP 201 and selection HTTP 200. Live weather and JSON routes passed.

The full upstream firmware still had too little runtime memory for reliable
status responses with this layout. Built and installed `3.1.0-homelab.1`,
variant `esp8266-dashboard`, from upstream v3.1.0 with unused ticker, usage,
radar and MQTT modes disabled. Themes, native clocks and notifications remain.
The build passed; the custom image's SHA-256 and source patch are retained
under `firmware/`. OTA returned HTTP 200. After reboot the device rejoined
the home network and reselected `bialystok-clock-v2` successfully. Its API
confirmed the custom version, synchronized Warsaw time and substantially more
available heap than the full build.

## Separate layouts and larger date — 2026-10-26

Active theme changed to `homelab-three-screens` (7,386 bytes, twenty-six layers,
two sources). The clock/date/weather layout is shown for forty seconds; the
original modern Raspberry Pi and Pi-hole layouts follow for twenty seconds
each. Native clocks appear only in the weather layout. Its date grew from
8 to 24 pixels and the clock was moved up six pixels to preserve spacing.

The original metric definitions and `/screen-v2.json` response are unchanged.
The active package copies those definitions with offscreen visibility bindings
driven by a shared phase from `/clock.json`. This avoids repeated theme-setting
writes or firmware replacement. The two sources declare eight fields each;
the phase is an additive field in the server response.

Thirteen backend tests pass. The official native renderer confirmed that the
Raspberry Pi and Pi-hole screens are byte-for-byte pixel-identical to the
original modern theme for identical sample values. The final package passed
native firmware validation; upload returned HTTP 201 and selection HTTP 200.
After activation the device had 12,312 bytes of free heap, remained connected,
and reported no selected-theme error.

## Services and backup screens — 2026-10-26

Added `homelab-five-screens` (7,384 bytes) using the same twenty-six layer
definitions as the previous theme. Only its metric source changes to
`/dashboard.json`. Clock/weather remains forty seconds; host, Pi-hole, services
and backups follow for twenty seconds each. Existing host, Pi-hole and weather
layout definitions are unchanged, including the 24-pixel date.

The new host exporter reads existing private monitor state and publishes a
separate allowlisted snapshot in `/var/lib/smalltv-dashboard`, every thirty
seconds. It preserves the original check timestamp. Private messages, Matrix
delivery state, URLs and credentials are excluded. The original monitoring
script, private-file permissions, five-minute checks and alerts are unchanged.
Only the new projection directory is mounted into the dashboard, read-only.

The Services page covers twelve configured containers plus Matrix/Vaultwarden
HTTP health. Backups reports the last good backup age when available, database
dump status and recovery-verification status. Unknown, missing, failed and
stale observations have explicit non-healthy display states.

Twenty-one Python tests passed, covering projection boundaries, queue/secret
exclusion, unknown recovery state, atomic publication permissions, stale and
future timestamps, backup age display bounds, original metric compatibility
and five-page scheduling. Systemd verified both exporter units, and the timer
is enabled. Native firmware validation accepted the package; live upload
returned HTTP 201 and selection HTTP 200.

## Screen warnings and night mode — 2026-10-26

Configured native night settings for Europe/Warsaw, 23:00–07:00, night brightness
zero. A temporary current-time window activated the firmware's `night` flag;
the final schedule was restored in a `finally` block and all saved clock
fields were read back successfully. Selected theme remained
`homelab-five-screens` and daytime brightness remained 60.

Added a notification worker inside the existing dashboard container. It reads
only the public projection, now including an additive disk-level field, and
sends bounded native overlays for problems, escalation, recovery and six-hour
reminders. The worker suppresses sends during 23:00–07:00 and re-evaluates live
conditions in the morning. All five native layouts are unchanged.

Claims and outcomes persist in the dedicated 0700 directory owned by UID 65534,
with 0600 files and a cooperating lock. Interrupted/uncertain POSTs are retained
without immediate replay; an explicit queue rejection permits a delayed retry.
The first startup encountered a new state-directory ownership error; ownership
was corrected and only the SmallTV container was restarted. The readiness
endpoint then confirmed the worker enabled with unchanged healthy conditions.

All thirty Python tests passed. A live end-to-end test used a separate temporary
state, real device preflight, a five-second `TEST` warning and the normal POST
transport; the device acknowledged it and delivery was persisted as confirmed.
The test state was removed. Original monitoring checks, Matrix messages and
production alert state were not modified by the test.
