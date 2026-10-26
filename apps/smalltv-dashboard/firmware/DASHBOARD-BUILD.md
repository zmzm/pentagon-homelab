# Dashboard firmware

Source: https://github.com/giovi321/smalltv-mod/tree/v3.1.0

The custom build retains JSON themes, native clock, notifications, Wi-Fi,
settings and OTA uploads. It disables unused ticker, usage, radar and MQTT
modes. Existing themes and filesystem layout remain compatible.

Version: `3.1.0-homelab.1`; variant: `esp8266-dashboard`.
The custom update asset is intentionally separate from upstream's full image.
Use manual OTA uploads of a newly rebuilt dashboard image for future updates.

To rebuild, check out upstream tag `v3.1.0`, apply `dashboard-build.patch` at
the repository root with `git apply --unidiff-zero dashboard-build.patch`,
install PlatformIO 6.1.19 in a Python virtual environment,
then run `pio run -e smalltv_dashboard`. The image is generated at
`.pio/build/smalltv_dashboard/firmware.bin`.

Observed toolchain: Espressif8266 platform 4.2.1, Xtensa GCC 10.3.0,
ArduinoJson 7.4.3. See `dashboard-build.json` for checksum, enabled features,
and build size. The build succeeded with 47,724 bytes of static RAM and
692,181 bytes of flash usage. The binary is 696,336 bytes.

The standard upstream v3.1.0 image remains in this directory for rollback;
the custom dashboard image is the one used for the current clock/weather UI.
