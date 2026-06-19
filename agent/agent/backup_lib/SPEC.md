# Backup engine (`backup_lib`)

Pulls a crash-consistent copy of a **running** VM's disk out of libvirt using the
push-mode backup API. Used by [[snapshot]] (`BaseSnapshot._take_image_file`) when the
domain is live.

File: `backup.py` → `VMBackup`.

- `__init__` `backup.py:14-17` — bound to a libvirt `virDomain` plus the target
  image id/doctype (for progress reporting).
- `backup_disk` `:19-40` — builds the `<domainbackup mode="push">` XML naming the disk
  device and destination file.
- `begin` `:42-72` — if the guest agent is present, `fsFreeze` → `backupBegin` →
  `fsThaw`; then polls `blockJobInfo` writing `progress` to the owning doc until
  complete; finally `chmod 777` the output (requires a NOPASSWD sudoers entry, noted
  inline `:71`).
- `get_status` `:74-81` — cur/end progress fraction.
- `host_has_qemu_ga` `:83-89` (cached) — probes `guestInfo()` to detect a qemu guest
  agent; gates fs-freeze (and surfaces as `fs_freeze` on the [[snapshot]]).
