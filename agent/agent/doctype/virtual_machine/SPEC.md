# Virtual Machine

A libvirt/KVM domain. The controller translates this Frappe document into libvirt
domain XML, drives the domain lifecycle, and builds a cloud-init seed ISO for
first-boot provisioning. The central object of the app.

Files: `virtual_machine.py` (controller), `*.jinja2` (cloud-init templates),
`virtual_machine.json` (schema), `virtual_machine.js` (desk Actions buttons).

## Schema (`virtual_machine.json`)
Autoname: `prompt` (the VM name is the libvirt domain name and cloud-init hostname).

| field | type | notes |
|---|---|---|
| `memory` | Int (MiB) | converted to KiB in XML |
| `number_of_vcpus` | Int | |
| `root_disk_size` | Int (GiB) | size of auto-created `vda` disk |
| `virtual_machine_image` | Link → Virtual Machine Image | source image (reqd) |
| `virtual_machine_type` | Data → [[virtual-machine-type]] | sizing label (reqd) |
| `disks` | Table → VM Disk | attached disks; `device` = `vda`,`vdb`… see [[vm-disk]] |
| `uuid` | Data (ro) | libvirt domain UUID + cloud-init instance-id; also the seed filename |
| `public_ip_address` | Data | empty ⇒ NAT `default` network; set ⇒ OVS bridge |
| `has_private_ip` | Check | attaches a second NIC on `br-int` (OVN) |
| `ssh_key`,`cloud_init` | Code | provisioning inputs |
| `state` | Select | **shadowed** by the live `state` property below |
| `network_interfaces` | Table | declared in schema but unused — NICs are derived, see below |

MAC/port identifiers are **computed**, not stored: `public_mac_address`,
`private_mac_address`, `port_uuid`, `seed_path` — `virtual_machine.py:759-789`.
`state` is a property that always queries libvirt (`:767-775`); the stored `state`
field is only written by the reconciler (`update_details`, below).

## Domain XML generation (the core)
Base domain template is `XML_CONFIG` in [[configuration-spec]]; `get_new_config()`
(`:820-821`) parses a fresh copy. `create_config()` (`:291-319`) mutates it: vcpus,
uuid, name, osinfo (from the image), memory, then devices + NICs.

- `create_device_config` `:321-353` — one `<disk>` per attached disk + the seed
  cdrom (`sda`). Snapshot disks expand their qcow2 backing chain by walking
  `Disk.backing_file` (see [[disk]]).
- `create_disk_config` `:355-428` — emits `<disk>` for `Volume` (file/qcow2/virtio),
  `Seed` (file/raw/sata cdrom), or `Ceph` (network/rbd/virtio with `<auth>` secret +
  monitor `<host>` list). `backing_chain` nests `<backingStore>` elements.
- `create_network_interfaces_config` `:430-444` + `generate_network_interface_xml`
  `:480-542` — public NIC is `Bridge`(OVS) when a public IP is set else `Network`
  (`default` NAT); private NIC is `Bridge` on `br-int` with the OVN `interfaceid`.
  `device_xml_only=True` returns a standalone `<interface>` for hot attach/detach.
- DOMAIN_STATE_MAP `:33-41` maps libvirt state ints → `Undefined/Running/Paused/Stopped`.

## Lifecycle hooks
- `__init__` `:71-88` — looks up the libvirt domain (unless Undefined); assigns a uuid.
- `before_insert` `:90-105` — if no `vda` disk, creates the primary [[disk]] from the
  image and appends it; `apply_config(define=False)`; `apply_image_config()` (seed).
- `on_change` `:111-122` — `apply_config()`, then declaratively reconcile disks +
  public/private NICs against `doc_before_save` (`:124-171`).
- `on_trash`/`after_delete` `:173-181` — undefine the domain, delete the `vda` disk.

## Operations (whitelisted via `virtual_machine.js`)
`start` `:192-208` (define+create / resume), `stop` `:210-224` (shutdown or
force-destroy), `pause` `:226`, `reboot` `:246`, `undefine` `:230-244`,
`apply_config` `:282-287`. Disk/volume hot-plug: `attach_disk`/`detach_disk`
`:544-559`, `get_volumes`/`attach_volumes` `:584-593`. Live NIC plug:
`attach/detach_network_interface` `:740-757`, `refresh_private_network_interface`
`:725-738`. The HTTP wrappers (by `uuid`) live in [[api-spec]].

## cloud-init seed (`apply_image_config` `:652-723`)
Renders `user-data.jinja2` (or raw `cloud_init`), `meta-data.jinja2`, and one of
`network-config.jinja2` / `network-config-without-public-ip.jinja2`, then packs them
into `{uuid}.img` (volid `cidata`) via `genisoimage`. Templates: root SSH key,
instance-id/hostname, eth0 static public IP + gateway, eth1 DHCP private.

## Provisioning entrypoints
- `new_vm_from_image` `:924-966` (whitelisted) → enqueues `_new_vm_from_image`
  `:881-921`, which provisions the image, creates the doc + (optional snapshot) disk,
  inserts and starts. Returns the `instance_id` (uuid) used for all later API calls.
- `provision_vmi_from_orchestrator` `:969-1027` — asks the orchestrator which peer
  agents hold the image (see [[orchestrator-client]]), downloads the qcow2 via
  `aria2c` from all peers, verifies sha256, creates the local [[virtual-machine-image]].
- `take_snapshot` `:595-650` — libvirt **external** disk snapshot that forks a qcow2
  and records a snapshot [[disk]] in the backing chain. Distinct from the S3-backed
  [[snapshot]] doctype.

## Reconciliation
`update_details` `:825-877` (whitelisted, `allow_guest`) is the inbound endpoint that
syncs DB state from real hypervisor state: marks missing VMs `Undefined`, and updates
memory/vcpus/state/disks via `db_set` with `polled=True` (which short-circuits
`validate`/`on_change`). `get_all_disks` `:873-877` maps file_path → Disk name (cached).

## Dead / unused in this file
`resize_and_restart` `:259-280`, `_restart` `:250-257`, `delete_disk` `:561-570`,
`generate_disk_xml` `:793-817`, `validate_root_device_exists` `:183-190`,
`setup_public_ip_address` `:446-449` (stub). No callers in-repo.
