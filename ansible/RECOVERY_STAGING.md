# Recovery source and encrypted-backup staging

This workflow prepares recovery material without extracting archives, overwriting a checkout, restoring databases or deploying services. The separate replacement machine still needs verified SSH access and identity as described in [remote preparation](REMOTE_PROVISIONING.md).

## Build a new bundle on the current server

```bash
cd ~/Documents/homelab
sudo python3 -B scripts/build_recovery_bundle.py --output /tmp/homelab-recovery-bundle-2026-10-21
```

Choose a new output directory outside the backed-up checkout each time; existing paths, symlink traversal and locations inside the source checkout are refused. Keeping staging outside the backup tree prevents recursive copies. Bundles under `/tmp` are temporary transfer material and disappear after cleanup/reboot; the original backup repository is unchanged. The builder includes current tracked and non-ignored pending source files, so uncommitted work is included. It excludes runtime/backup directories, private inventories, real Vault files, dotenv secrets and private keys. The source archive is not a Git history clone. `manifest.json` records the Git HEAD, creation time, selected snapshot and every artifact's size/hash.

The latest `plan:pentagon-backup` snapshot is copied using Restic into a separate encrypted repository, with source/destination locking and a complete `check --read-data`. No plaintext application restore is created for staging. It uses the existing Backrest repository password; keep that password separately in your password manager. No unlock password is included. Failed builds remove only their newly created directory. A sudo-invoking user receives ownership of the encrypted bundle so it can be used by their controller. This local staging bundle is not the deferred external backup.

## Copy to a verified replacement

The bundle must be accessible on the Ansible controller. Then:

```bash
cd ~/Documents/homelab/ansible
ansible-playbook -i inventory.ssh.yml stage-recovery.yml \
  -e homelab_recovery_bundle=/absolute/controller/path/to/recovery-bundle --check
ansible-playbook -i inventory.ssh.yml stage-recovery.yml \
  -e homelab_recovery_bundle=/absolute/controller/path/to/recovery-bundle
```

The playbook verifies the replacement identity first and stages only into `/var/lib/homelab-recovery-staging/<bundle-id>`. It atomically reserves a new private directory; an existing directory is refused. Free space is checked, all artifact hashes and source tar member names are verified after transfer, and a failed transfer removes only the directory reserved by that invocation. The archive and encrypted repository are left inactive for a separate reviewed recovery step. Abrupt process/power loss can leave an incomplete staging directory; inspect it manually instead of overwriting it.

A private temporary staging base is supported for fixtures only. Production checkout paths and symlinked destinations are refused. Successful staging does not establish application recovery or install a checkout, and no separate-host transfer was performed in the current validation. The staging role itself passed local temporary-root tests, including real encrypted repository transfer, overwrite refusal and corruption cleanup.
