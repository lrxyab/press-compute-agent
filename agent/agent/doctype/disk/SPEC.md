# Disk

A block volume backing a [[virtual-machine]]. Two storage media: a local `File`
(qcow2 under `{CONFIG_PATH}/disks/`) or a `Ceph` RBD image. A Disk may be a fresh
blank volume, a copy of a [[virtual-machine-image]], or a qcow2 snapshot in a
backing chain.

Files: `disk.py` (controller), `disk.json` (schema). `DISKS_ROOT` =
`{CONFIG_PATH}/disks` — `disk.py:23`; CONFIG_PATH from [[configuration-spec]].

## Schema (`disk.json`)
Autoname: `format:{uuid}`. The `uuid` is also the on-disk filename / RBD image name.

| field | type | meaning |
|---|---|---|
| `size` | Float (GiB) | |
| `storage_medium` | Select `File`/`Ceph` | selects every code path below |
| `is_primary_disk` | Check | the bootable `vda` root disk |
| `virtual_machine_image` | Link | source image when copying |
| `from_virtual_machine_image` | Check | created as a copy of a VMI |
| `is_snapshot` | Check | a qcow2 fork; not created/resized directly |
| `backing_file` | Link → Disk | parent in the qcow2 backing chain |
| `from_snapshot` / `snapshot` | Check / Link → [[snapshot]] | restored from an S3 snapshot |
| `file_path` | Data (ro) | resolved path / `pool/uuid`; set on insert |
| `status` | Select `Available`/`Unavailable` | |

## Path resolution — `get_path` `disk.py:78-83`
`Ceph` → `{def_rbd_pool}/{uuid}` (from Compute Settings); `File` →
`{DISKS_ROOT}/{uuid}.qcow2`.

## Creation — `before_insert` `disk.py:54-68`
Sets `file_path`. Snapshots return early (the qcow2 fork is made by the VM, see
[[virtual-machine]] `take_snapshot`). Primary / from-image disks →
`create_system_image_from_vmi` `:89-104` (Ceph `copy` via [[ceph-client]], or
`shutil.copy` for File; media must match), then `set_disk_size`. Blank disks →
`create_disk` `:114-123` (Ceph create, or `qemu-img create -f qcow2`).

## Resize — `set_disk_size` `disk.py:135-147`, growth-only
File path picks between offline and live based on `use_qemu_resize` `:149-156`
(true unless the owning VM is `Running`): offline `qemu-img resize`; live
`increase_vm_disk_size` `:158-161` → `domain.blockResize`. Ceph → `ceph.resize`.
Triggered on `size` change via `on_change` `:106-112` and the HTTP
`increase_disk_size` in [[api-spec]].

## Deletion — `after_delete` `disk.py:125-133`
Ceph `delete_disk`; File `os.remove` (ignores missing).

## Restore from snapshot — `create_disk_from_snapshot` `disk.py:164-177`
Downloads the snapshot object from S3 (`get_s3_client_and_credentials`, see
[[snapshot]]) into a new qcow2 and records a `from_snapshot` Disk. Called by
`_new_vm_from_image` in [[virtual-machine]].

`ceph` property `:70-76` builds a [[ceph-client]] with credentials from Compute
Settings.
