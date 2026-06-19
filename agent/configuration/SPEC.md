# Configuration (`agent/configuration`)

Static, host-level wiring shared across the app.

- **`paths.py:1-3`** — `CONFIG_PATH = frappe.get_conf().compute_config_path or
  "/etc/frappe-compute/"`. The root of all on-host artifacts. Subdirectories used by
  the code: `images/` (base VMIs), `disks/` (qcow2 volumes + snapshot forks),
  `seeds/` (`{uuid}.img` cloud-init ISOs), `snapshots/` (capture staging).
- **`connections.py:1-5`** — `libvirt_connection()` → `libvirt.open("qemu:///system")`.
  The single libvirt entrypoint used everywhere ([[virtual-machine]], etc.).
- **`configs.py:1-151`** — `XML_CONFIG`, the base libvirt **domain XML template**
  (q35/KVM, host-passthrough CPU, PCIe topology, serial/VNC/virtio devices, no disks
  or NICs). [[virtual-machine]] `create_config` parses a fresh copy and fills in
  vcpus/uuid/name/osinfo/memory and appends disk + NIC elements.

`configuration/__init__.py` is empty. (The unused `libvirt_api.py` imports
`CONFIG_PATH` from here — see [[agent-app]].)
