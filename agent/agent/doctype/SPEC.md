# DocType layer (`agent/agent/doctype`)

Every Frappe DocType is a directory of `{name}.py` (controller), `{name}.json`
(schema), `{name}.js` (desk form). Each major doctype has its own co-located SPEC;
the small supporting doctypes are documented here.

## Major doctypes (own SPECs)
- [[virtual-machine]] — the KVM domain; XML generation, lifecycle, provisioning.
- [[disk]] — File/Ceph block volumes; backing chains.
- [[snapshot]] — S3 backups + the shared `BaseSnapshot` capture engine.
- [[virtual-machine-image]] — bootable images; peer-to-peer distribution.

## Supporting doctypes
**Compute Settings** `compute_settings/` — **single** doctype; the central config
store (orchestrator creds + URL, OVS bridge, public/private IP & NIC, Ceph mgr creds &
pool & monitors, libvirt RBD secret). Read across the app via
`frappe.db.get_single_value` / `get_decrypted_password`. Controller is a plain
`Document` plus `update_orchestrator_credentials` `compute_settings.py:37-44`
(Administrator-only). Schema: `compute_settings.json`.

**Virtual Machine Type** `virtual_machine_type/` — a sizing template (`memory`,
`number_of_vcpus`, `root_disk_size`). Referenced by name from [[virtual-machine]]
`virtual_machine_type`. Seeded via `fixtures/virtual_machine_type.json` (CPX22, CPX32);
fixtures filter in [[agent-app]] hooks. Plain `Document`.

**VM Disk** `vm_disk/` — child table on Virtual Machine `disks`: `disk` (Link) +
`device` (`vda`,`vdb`…). `size` is a live property reading the [[disk]]
`vm_disk.py:24-26`.

**Network Bridge** `network_bridge/` — `on_submit` `network_bridge.py:22-23` runs
`ovs-vsctl add-br {name}` to create an OVS bridge on the host.

**Network Interface** `network_interface/` — child table (`name1`, `type`
Network/Bridge/Direct, `mac_address`). Declared on the VM schema but **unused** — the
[[virtual-machine]] controller derives NICs from computed MAC properties instead.
