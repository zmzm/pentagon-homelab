# SmallTV JSON dashboard

Target: GeekMagic SmallTV-Ultra ESP8266, stock Ultra-V9.0.40.
Firmware: smalltv-mod 3.1.0-homelab.1, a custom ESP8266 dashboard build based on
upstream v3.1.0. It keeps themes, clocks and notifications while omitting unused
ticker, usage-meter, radar and MQTT modes to leave enough RAM for the display.
The upstream lean image cannot be used because it excludes themes.

The active Homelab Five Screens theme uses `/clock.json` for weather and
`/dashboard.json` for metrics and monitoring, polling each every ten
seconds at `http://192.168.0.185:8096`. A shared layout phase selects a dedicated
clock/weather screen for forty seconds, followed by the original Raspberry Pi
and Pi-hole screens, then services and backups, for twenty seconds each.
Clocks and date appear only on the weather screen. Its date uses a 24-pixel font.
The Pi returns two rotating pages: host temperature/memory/load/disk and Pi-hole
statistics from the existing adapter. The device draws all text and shapes.
The `.stheme` package contains a JSON manifest only, without bitmap assets.
The active theme has twenty-six native text/shape layers and two JSON sources,
including the weather symbol and thermometer. Source is in
`theme-five-screens/theme.json`; the installable package is
`homelab-five-screens.stheme`, with ID `homelab-five-screens`.
The metric layouts are copied from the original `theme-modern` and only gain
visibility bindings. Their firmware-rendered pixels match the original theme
exactly for the same input values. The larger date belongs to the weather layout.
The earlier themes and `/screen.json` and `/screen-v2.json` endpoints remain
available for rollback.

Current weather comes from [Open-Meteo](https://open-meteo.com/en/docs) for
53.13333, 23.16433 (Bialystok, Poland), using model-based current conditions.
A separate worker refreshes it every ten minutes, retrying failures after one
minute without blocking host checks or HTTP requests. Model timestamps older
than thirty minutes are labeled stale, and values older than two hours are
hidden. Last successful data survives temporary upstream errors in memory.
No API key is required. The small weather timestamp is explicitly UTC (`Z`);
the large clock uses local Warsaw time with summer/winter time rules.

The collector refreshes every fifteen seconds, while pages rotate every twenty
seconds. Load is the host's one-minute load average, not CPU percentage. Disk
free space is measured on the filesystem containing `disk-probe`; keep it on
the root filesystem to monitor root space. The Pi-hole page shows unavailable
data explicitly. The timestamp is UTC and identifies the last collection.
If the collector stops while HTTP is still running, values are marked stale
after 45 seconds. If the entire server or network disappears, firmware retains
the last values and timestamp; this version does not show an automatic offline
overlay. Firmware text uses ASCII, so labels are English.

## Deployment

Copy this directory to `homelab/apps/smalltv-dashboard`, then run
`docker compose -f compose.yaml up -d --build` there. The service uses the
existing `proxy` network and publishes port 8096 only on the Pi's LAN address.
It runs without root, capabilities or Docker socket access. Read-only host
proc/sys mounts provide metrics; the empty disk-probe directory provides a
filesystem space probe. No credentials are included in JSON.

Change SMALLTV_BIND_IP and the theme's data URL if the Pi's LAN IP changes.
Reserve Pi and SmallTV addresses in the router for stable operation.

## Device installation

Firmware files and GitHub-provided SHA-256 digests are in `firmware/`.
The release digests are checked at download; they are not an independent code
audit. Source: https://github.com/giovi321/smalltv-mod/releases/tag/v3.1.0

The installed custom image is `firmware/smalltv-mod-firmware-dashboard.bin`.
Its checksum, feature flags and build metadata are in `dashboard-build.json`,
with the source changes in `dashboard-build.patch`. See
[rebuilding the firmware](firmware/DASHBOARD-BUILD.md). Updates to this custom
variant are manual; its asset name prevents the upstream updater from silently
replacing it with the full image that previously ran short of RAM.

For a device still on stock firmware, upload `smalltv-mod-loader.bin` at its
`/update`. The loader creates the
open `SmallTV-Loader` AP at 192.168.4.1. Join it with the Pi's unused wlan0
while keeping Ethernet active and avoiding a default route on wlan0.
Upload `smalltv-mod-firmware-dashboard.bin` at `http://192.168.4.1/update`.
Join `SmallTV-Setup`, configure the existing home Wi-Fi, then reconnect to the
device on the LAN. Install `homelab-five-screens.stheme` under Display > Theme clocks
and activate it. Temporary Wi-Fi profiles should not autoconnect.
When replacing themes on this ESP8266, switch to stocks mode first to release
the old theme. Clock settings require both `tz: Europe/Warsaw` and
`tzPosix: CET-1CEST,M3.5.0,M10.5.0/3`; the display label alone does not set the
actual timezone.

The new firmware replaces stock software and may reformat its filesystem.
The original device flash has not been dumped; a byte-for-byte rollback backup
requires UART access. The stock vendor distributes Ultra-V9.0.40 separately.

## Verification

Run `python3 -B -m unittest discover -s . -v`.
The theme package was built with v3.1.0's official packer and actual C++
firmware validator, using ArduinoJson v7.2.0 and Arduino_GFX v1.5.0.
Live HTTP and device checks must be recorded separately from those tests.

## Services and backups

`smalltv-status-export.timer` runs the small host exporter every thirty seconds.
It reads the existing private `/var/lib/homelab-monitor/state.json` and the
monitor configuration, then atomically publishes only allowlisted levels,
numeric backup ages and the original check timestamp to
`/var/lib/smalltv-dashboard/status.json`. The output directory is 0755 and the
file is 0644; the original monitoring state retains its private permissions.
Raw messages, notification queues, URLs and credentials are never published.
The dashboard mounts only this public directory, read-only. It receives no
Docker socket or monitoring credentials.

Install the exporter before starting the updated Compose service:

```bash
cd /home/pentagon-admin/Documents/homelab/apps/smalltv-dashboard
sudo systemd-analyze verify smalltv-status-export.service smalltv-status-export.timer
sudo install -m 0644 smalltv-status-export.service smalltv-status-export.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start smalltv-status-export.service
sudo systemctl enable --now smalltv-status-export.timer
sudo install -d -m 0700 -o 65534 -g 65534 /home/pentagon-admin/Documents/homelab/data/smalltv-dashboard
docker compose -f compose.yaml up -d --build
```

The original monitor still collects results every five minutes. Exporting its
snapshot more often does not perform extra checks or send Matrix messages.
The Services screen counts the configured twelve core container checks and
two HTTP checks (Matrix and Vaultwarden). Containers without a configured
Docker health check are checked for running status only. Other application
projects and the personal-agent stack are outside this monitor's current scope.

Backups shows the age of the last successful real Backrest backup when the
existing result reports that age, the database-dump status (`DB`), and the
isolated recovery-verification result (`TEST`). That result does not validate
the incomplete external USB copy. If the latest backup check fails without
reporting a usable success age, the main value is `--`, with an alert status.
An initial recovery run is shown as unknown, not as a successful restore.

Snapshots older than fifteen minutes are marked `STALE`; missing, malformed or
future-dated snapshots do not display a healthy status. The exporter does not
modify the original monitoring schedule, state, queue or Matrix delivery.
Existing API consumers retain `/screen.json` and `/screen-v2.json`; the new
`/dashboard.json` endpoint adds the two monitoring pages. The weather response
layout phase now follows a 120-second cycle.

## Screen warnings and night mode

The device's native night mode turns the backlight off from **23:00 to 07:00
Europe/Warsaw**, including seasonal clock changes. Daytime brightness remains
the existing device setting. `night-mode.json` contains the exact partial
configuration applied to `/api/config`. The firmware runs this schedule
itself; its trusted-NTP gate prevents entering night mode with an untrusted
clock. The alert worker uses the same 23:00–07:00 quiet window and does not
contact the notification API at night. If changing this schedule, update both
the device settings and `alert_worker.quiet_hours` together.

The dashboard polls the public monitoring summary every fifteen seconds for
screen alerts. Critical issues use a red overlay, warnings and unknown results
use yellow, and recovery uses green. Problems display for fifteen seconds and
recovery for eight seconds; native firmware then restores the selected theme.
The source still updates on the existing monitor's five-minute cadence.
Coverage includes configured containers, Matrix/Vaultwarden HTTP health,
backup/dump/restore results, disk status and missing/stale monitoring data.

Alerts appear on state changes; unchanged issues remind after six hours.
Critical changes take priority over warnings, then recoveries. Quiet hours
leave the last notified levels untouched, so morning evaluation shows only
currently relevant changes and reminders, not problems that appeared and
resolved entirely overnight. Screen alerts are independent of Matrix delivery.

Deduplication state is `/state/alerts.json`, mounted from ignored
`data/smalltv-dashboard`, directory 0700 and file 0600, owned by UID/GID 65534.
A cooperating file lock limits the state to one worker. A delivery claim is
atomically saved and fsynced before each POST. Confirmed acknowledgments are
recorded. After an uncertain POST or interrupted claim, that event is not
immediately replayed; a later level change or six-hour reminder can produce a
new notification. This trades possible loss after uncertainty for avoiding
duplicate overlays. Failed read-only preflight checks retry on the next poll;
an explicit queue-full response backs off sixty seconds. Corrupt state stops
notification delivery instead of resetting deduplication.

`/notifications.json` reports worker readiness, last evaluation and the latest
delivery outcome without exposing check contents. Unit tests exercise quiet
boundaries in winter/summer, priority, recovery, restart deduplication, claims
before dispatch, queue rejection and ambiguous delivery. Live verification used
a separate temporary test state and a five-second overlay labeled `TEST`;
production monitoring results were not changed.
