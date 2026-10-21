# Independent availability monitoring

Status: deferred by the user on 2026-10-19. No external monitoring account is connected, and no remote monitor or notification recipient has been created or verified. Retain these settings for a possible future revisit; account creation and activation are not current tasks. Weekly recovery verification remains active.

Use hosted Better Stack Uptime monitoring, with email alerts to the account owner. The monitor runs outside the homelab, so it can detect a server, power, home Internet or tunnel outage even while the local Matrix alert bot is unavailable. A reachable endpoint does not prove every homelab service is healthy; the local checks continue to cover those services.

## Activate in your own account

1. Create a Better Stack account from [its monitoring page](https://betterstack.com/uptime) and verify your email address. Use an email provider independent of this server. Select a plan that supports the settings below; no paid subscription has been authorized or provisioned here.
2. Open **Monitors → Create monitor**. Configure the settings below and choose yourself as the primary responder, with **email** notifications. Save the monitor and check it reports **Up**.
3. Use the provider's notification test, if available, and confirm the email arrives. This step is intentionally left to the account owner; no test messages have been sent by the repository tools.

| Setting | Value |
| --- | --- |
| Name | Pentagon — public Matrix availability |
| URL | `https://matrix.pentagonlab.org/_matrix/client/versions` |
| Check type | Response contains keyword |
| Required keyword | `"versions"` (including quotation marks) |
| Interval | 3 minutes |
| Request timeout | 15 seconds |
| Confirm failure before alerting | 3 minutes |
| Confirm recovery | 3 minutes |
| TLS certificate verification | Enabled |
| Follow redirects | Disabled |
| Request header | `User-Agent: Pentagon-Uptime-Monitor/1.0` |
| Notifications | Email to your verified account; routine successful checks stay quiet |

The expected response is HTTP 200 with a nonempty JSON `versions` array. Checking the keyword helps reject a generic proxy/error page. The three-minute confirmation period reduces alerts for brief restarts; detection also depends on the check schedule. The public URL needs no login, token or additional firewall port. Keep the provider's notification destination independent of Matrix on this host.

Preflight on 2026-10-19: this public HTTPS endpoint returned HTTP 200 with the expected JSON and keyword using the explicit monitoring user agent above. Python's default user agent received HTTP 403 from Cloudflare, so keep the explicit request header and verify the provider's real checks after activation. No Cloudflare rules were changed. A request originating on this host is not a verified external-provider check.

`external-monitor.json` contains the corresponding [Better Stack create-monitor API](https://betterstack.com/docs/uptime/api/create-a-new-monitor/) request body for later automation. It contains no credentials. Account registration, resource creation and email delivery are still required; a configuration file alone does not activate external monitoring. Never paste an API token into chat or commit one to Git.

## Verify after activation

- Confirm the provider has completed a real check and reports the monitor as Up.
- Confirm email notification delivery using the provider's test facility. Do not shut down production to test this.
- If this work is resumed, record the monitor ID and activation date here after verification. Improvement #2 remains deferred until the user chooses to resume it.

Sources: [monitor and email setup](https://betterstack.com/docs/uptime/monitoring-start/), [keyword monitoring](https://betterstack.com/docs/uptime/keyword-monitor/), and [API parameters](https://betterstack.com/docs/uptime/api/create-a-new-monitor/).
