# HTTP API (`agent/api`)

The whitelisted REST surface the **orchestrator** calls to drive this agent. Every
handler is `@frappe.whitelist(methods=["POST"])` unless noted, and addresses VMs by
their `instance_id` (the [[virtual-machine]] `uuid`). Handlers are thin wrappers that
load the doc and delegate to controller methods.

Files: `virtual_machine.py`, `disk.py`, `snapshot.py`, `virtual_machine_image.py`.

## `api/virtual_machine.py`
`stop` `:4-7`, `start` `:10-13`, `terminate` `:16-26` (clears the VMI back-reference
then deletes the VM → cascades disk/domain teardown), `reboot` `:29-32`,
`resize` `:35-51` (rejects a running VM; sets memory/vcpus/type and saves),
`remove_public_ip` `:54-62` (detaches the public NIC by clearing the IP).

## `api/disk.py`
`increase_disk_size` `:11-20` (growth-only), `attach_disk` `:23-48` (auto-picks the
next free `vd*` device), `detach_disk` `:51-67`, `sync` `:70-73`. Mutating the VM's
`disks` table triggers the declarative reconcile in [[virtual-machine]] `on_change`.

## `api/snapshot.py`
`new` `:9-19` (create a [[snapshot]] doc + `take_image`), `sync` `:22-30` (GET; returns
status/progress/fs_freeze), `delete` `:33-37` (`mark_unavailable`).

## `api/virtual_machine_image.py`
`new` `:9-21` — capture a [[virtual-machine-image]] from a VM (`is_from_vm`,
status `Ongoing`) and `take_image`.

VM **creation** does not live here — it is `new_vm_from_image` on the controller in
[[virtual-machine]]. Other inbound endpoints exposed directly from controllers:
`update_details` (reconciler) and `download_vmi` (peer image serving).
