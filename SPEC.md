# Agent — Frappe Cloud Compute Plane

The **agent** is a Frappe app that runs on a hypervisor host and turns documents into
real infrastructure: KVM/QEMU virtual machines (via libvirt), their block disks (local
qcow2 or Ceph RBD), point-in-time snapshots (S3), and bootable images. It is a worker
driven over HTTP by a central **orchestrator** (the control plane, a separate app); it
holds no scheduling logic of its own — it executes and reports state.

This file is the apex of a spec DAG. Each directory of real material has a co-located
`SPEC.md` that conceptually covers it and points into code as `file.py:start-end`
(line ranges relative to that SPEC's own directory). Start here, follow a `[[link]]`,
land on a local SPEC, jump to the code.

## How it fits together
```
orchestrator ──HTTP──▶ agent/api ──▶ DocType controllers ──▶ host resources
                                        │                       ├─ libvirt/qemu (VMs)
                                        │                       ├─ qcow2 files / ceph-mgr (disks)
                                        │                       ├─ S3 (snapshots)
                                        │                       └─ ovs-vsctl / OVN (networking)
```
A VM is identified everywhere by its `instance_id` = the [[virtual-machine]] `uuid`
(also the libvirt domain UUID and cloud-init instance-id). All host artifacts live
under `CONFIG_PATH` ([[configuration-spec]]).

## Core flows (entry → spec)
- **Create a VM**: `new_vm_from_image` enqueues a worker that provisions the image
  (peer download or local), creates the root [[disk]] from the [[virtual-machine-image]],
  builds domain XML + a cloud-init seed ISO, then starts it — [[virtual-machine]].
- **Lifecycle** (start/stop/reboot/resize/terminate/public-IP): orchestrator → [[api-spec]]
  → controller methods on [[virtual-machine]].
- **Disks** (attach/detach/grow, File vs Ceph, backing chains): [[disk]] + [[ceph-client]].
- **Snapshot** (capture running disk → qcow2 → S3): [[snapshot]] + [[backup-engine]].
- **Image** (capture a VM into a reusable bootable image, serve to peers): [[virtual-machine-image]].
- **State reconciliation** (DB ⇐ real hypervisor state): `update_details` in [[virtual-machine]].

## Spec DAG index
| `[[slug]]` | path |
|---|---|
| [[agent-app]] | `agent/SPEC.md` — app wiring, orchestrator client, host utils |
| [[orchestrator-client]] | `agent/SPEC.md` (utils.py section) |
| [[configuration-spec]] | `agent/configuration/SPEC.md` |
| [[api-spec]] | `agent/api/SPEC.md` |
| [[doctype-layer]] | `agent/agent/doctype/SPEC.md` (+ supporting doctypes) |
| [[virtual-machine]] | `agent/agent/doctype/virtual_machine/SPEC.md` |
| [[disk]] | `agent/agent/doctype/disk/SPEC.md` |
| [[snapshot]] | `agent/agent/doctype/snapshot/SPEC.md` |
| [[virtual-machine-image]] | `agent/agent/doctype/virtual_machine_image/SPEC.md` |
| [[virtual-machine-type]], [[vm-disk]] | supporting doctypes, in `agent/agent/doctype/SPEC.md` |
| [[ceph-client]] | `agent/agent/ceph_lib/SPEC.md` |
| [[backup-engine]] | `agent/agent/backup_lib/SPEC.md` |

## Host dependencies
libvirt + qemu-kvm (`qemu:///system`), `genisoimage` (seed ISO), `aria2c` (peer image
download), `ovs-vsctl` (bridges), OVN `br-int` (private networking), a Ceph Manager
Dashboard API (RBD), and S3 (snapshots). Credentials and endpoints are held in the
**Compute Settings** single doctype ([[doctype-layer]]).

## Conventions
- Frappe app layout: each DocType is `controller.py` + `schema.json` + `form.js`; the
  `# begin: auto-generated types` block is generated, not hand-edited.
- `CPX%` Virtual Machine Type rows ship as fixtures ([[agent-app]]).
- Known dead code is flagged in the local SPECs (e.g. `libvirt_api.py`, several
  unused `VirtualMachine` methods). The `state_reader` Go helper was removed (it posted
  to a non-existent endpoint).
