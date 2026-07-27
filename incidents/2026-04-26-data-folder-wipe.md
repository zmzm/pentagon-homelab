# 🚨 Incident Report

Incident postmortem template for the Pentagon homelab.

---

# Incident Information

Incident ID: HL-2026-03-24-001

Date: 2026-03-24

Severity:
- Critical

Status:
- Resolved

---

# Summary

Accidental deletion of the entire `data/` directory in the homelab, resulting in loss of all persistent service data.

All services relying on Docker bind mounts became non-functional.

System was successfully restored using Restic backups.

---

# Impact

What was affected:

- All stateful services lost their data directories
- Multiple services failed or became unusable

Affected services:

- Vaultwarden (critical data risk)
- Pi-hole
- Unbound
- Caddy
- Homepage
- Portainer
- Matrix
- Backrest

Impact details:

- Vaultwarden data temporarily unavailable
- DNS services disrupted
- Internal web services inaccessible
- Homelab effectively non-operational

---

# Timeline

17:00 — Accidental deletion of `~/homelab/data/`  
17:01 — Services begin failing / behaving unexpectedly  
17:05 — Realization that all persistent data is missing  
17:08 — Verification of missing directories  
17:10 — Identification of Restic backup repository  
17:12 — Initial attempt to access repository (permission issues)  
17:15 — Repository accessed with sudo  
17:18 — Snapshots successfully listed  
17:20 — Test restore initiated to `restore-test/`  
17:22 — Permission issues identified and resolved (chown)  
17:25 — Verification of restored data structure  
17:27 — Full restore initiated  
17:30 — Permissions fixed on restored data  
17:32 — Docker services restarted  
17:35 — Services confirmed operational  

---

# Detection

How was the incident discovered:

- Manual action (user error)
- Immediate service failure after deletion

Commands used:

    ls ~/homelab/data

---

# Root Cause

Human error: accidental deletion of the entire `data/` directory containing all persistent service volumes.

Contributing factors:

- No confirmation or safeguards before deletion
- Critical data stored in a single directory
- No immediate backup verification routine

---

# Investigation

Commands and tools used:

Check data directory:

    ls ~/homelab/data

Locate restic repository:

    ls ~/homelab/backups/restic

List snapshots:

    sudo RESTIC_REPOSITORY=/home/pentagon-admin/Documents/homelab/backups/restic restic snapshots

Test restore:

    restic restore a2a12cf8 --target ~/restore-test

Fix permissions:

    sudo chown -R pentagon-admin:pentagon-admin ~/restore-test

---

# Resolution

Steps taken:

1. Identified valid Restic repository  
2. Retrieved latest snapshot (`a2a12cf8`)  
3. Performed test restore to verify integrity  
4. Restored full data directory  
5. Fixed file ownership  
6. Restarted all Docker services  

Commands:

    restic restore a2a12cf8 --target ~/
    sudo chown -R pentagon-admin:pentagon-admin ~/Documents/homelab
    docker compose up -d

---

# Recovery Verification

Verification steps:

Check restored data:

    ls ~/homelab/data

Check containers:

    docker ps

Manual checks:

- Vaultwarden UI accessible  
- Pi-hole admin panel working  
- Homepage loads correctly  

---

# Lessons Learned

- Separation of `apps/` and `data/` is critical and effective  
- Backups are only useful if they are tested — and this one worked  
- Running restore tests before full recovery prevents mistakes  
- Permissions (`root vs user`) are a common recovery pitfall  
- Accidental deletion is a realistic and common failure mode  

---

# Preventive Actions

Add safer rm:

    alias rm='rm -i'

Additional improvements:

- Use `trash-cli` instead of permanent deletion  
- Schedule automated backup verification (test restore)  
- Add offsite backup (S3 / external disk)  
- Document recovery procedure  
- Consider filesystem snapshots (btrfs / zfs)  

---

# Related Files

apps/  
data/  
backups/restic  
backups/backrest  
