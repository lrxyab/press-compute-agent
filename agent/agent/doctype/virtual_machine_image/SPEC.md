# Virtual Machine Image (VMI)

A bootable OS image (qcow2 `File` or `Ceph` RBD) that disks are cloned from when
creating a [[virtual-machine]]. Subclasses `BaseSnapshot`, so capturing a VMI from a
running VM reuses the same engine as [[snapshot]] — the only difference is a VMI
keeps its file **locally** (never uploaded to S3) for fast disk creation.

Files: `virtual_machine_image.py` (controller), `virtual_machine_image.json` (schema),
`virtual_machine_image.js` (Take Image button).

## Schema (`virtual_machine_image.json`)
Autoname `prompt`. Key fields: `status`
(`Draft`/`Pending`/`Ongoing`/`Available`/`Unavailable`), `file_path`,
`storage_medium` (`File`/`Ceph`), `osinfo` (libosinfo id stamped into domain XML by
[[virtual-machine]] `create_config`), `sha256sum`, `size`, `is_from_vm`,
`virtual_machine`, `disk`.

## Controller `virtual_machine_image.py`
- `VirtualMachineImage(BaseSnapshot)` `:13-52` — `__init__` sets `device` (default
  `vda`) and `image_path` (`images` for a base image, `disks` for a snapshot-style
  capture) via `set_device`/`set_image_path` `:40-52`. Capture/disk-creation behaviour
  is entirely inherited — see [[snapshot]].
- `get_vmi_download_token` `:55-60` — asks the orchestrator for a short-lived JWT
  ([[orchestrator-client]]).
- `download_vmi` `:64-81` (whitelisted GET, `allow_guest`) — verifies the JWT
  (`method=get_vmi`) and streams the local qcow2 to a peer agent. This is the serving
  side of `provision_vmi_from_orchestrator` in [[virtual-machine]] (peer-to-peer image
  distribution via `aria2c`). Ceph serving is not implemented.

Creation from a VM is triggered by the `new` endpoint in [[api-spec]].
