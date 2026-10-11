# 🚨 Incident Report

Incident postmortem template for the Pentagon homelab.

---

# Incident Information

Incident ID:

Date:

Severity:
- Low
- Medium
- High
- Critical

Status:
- Resolved
- Monitoring
- Open

---

# Summary

Short description of the incident.

Example:

DNS loop caused Pi-hole to stop resolving external domains.

---

# Impact

What was affected?

Examples:

- DNS resolution failed
- Internal services unavailable
- Web services unreachable

Affected services:

- Pi-hole
- Unbound
- Caddy
- etc

---

# Timeline

Record key events during the incident.

Example:

19:10 — DNS resolution stopped working  
19:12 — Confirmed external domains not resolving  
19:15 — Investigated Pi-hole logs  
19:20 — Identified DNS loop between Pi-hole and Unbound  
19:25 — Updated upstream DNS configuration  
19:27 — DNS resolution restored

---

# Detection

How was the incident discovered?

Examples:

- Manual testing
- Browser error
- Monitoring alert
- DNS query failure

Command used:

curl -fsS http://127.0.0.1:8008/health

or

curl http://vault.home.arpa

or

dig google.com

---

# Root Cause

Describe the underlying cause of the problem.

Example:

Pi-hole upstream DNS was incorrectly set to itself, creating a DNS loop.

---

# Investigation

Commands and tools used during investigation.

Examples:

Check running containers:

docker ps

Check logs:

docker logs pihole

Check monitoring:

curl -fsS http://127.0.0.1:8008/health

Test DNS:

dig google.com

Test specific resolver:

dig google.com @127.0.0.1 -p 5335

Check ports:

ss -tulnp

Search logs:

grep -i error /var/log/syslog

---

# Resolution

What was done to fix the issue?

Example:

Updated Pi-hole upstream DNS to point to Unbound (127.0.0.1:5335).

Restarted services:

docker restart pihole
docker restart unbound

---

# Recovery Verification

Steps used to confirm the system was working again.

Example:

dig google.com

curl http://vault.home.arpa

docker ps

---

# Lessons Learned

What did we learn from this incident?

Examples:

- DNS loops are easy to create with incorrect upstream configuration
- Targeted health checks help detect service problems

---

# Preventive Actions

Steps to prevent similar incidents in the future.

Examples:

- Document DNS configuration
- Add alerts for failed backups, low disk space, and unavailable services
- Add automated health checks

---

# Related Files

Links to relevant configs or logs.

Examples:

- apps/pihole
- apps/unbound
- apps/caddy/Caddyfile
