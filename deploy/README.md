# Frappe Compute Agent — pyinfra production deploy

Provisions the **agent** (the Frappe Cloud Compute plane worker) onto a clean
**Ubuntu 24.04** host: libvirt/KVM + qemu, Open vSwitch + an **OVN client**
(chassis) wired to your OVN controller, a `frappe` user, a bench with the app and
its site, all behind **Caddy** as the reverse proxy.

The reference bash script was the starting point; this fills in the gaps a real
production box needs (a proper user model, MariaDB, supervisor, socket
permissions, kernel forwarding, AppArmor handling, OVN chassis config).

## Layout

```
deploy/
├── inventory.py                 # the target host(s) + per-host overrides
├── deploy.py                    # entrypoint — runs the tasks in order
├── group_data/all.py            # ★ ALL configuration variables live here ★
├── tasks/                       # one @deploy() per concern
│   ├── packages.py  users.py  config_dirs.py  database.py
│   ├── libvirt.py   networking.py  bench.py  caddy.py
├── templates/                   # Caddyfile, public-bridge netplan (jinja2)
└── files/                       # static drop-ins (sysctl, sudoers, mariadb, …)
```

## Configure

Everything is driven from **`group_data/all.py`** (shared defaults) and
**`inventory.py`** (host list + per-host overrides). Edit those two files.

At minimum change: `site_name` / `web_domain`, `site_admin_password`,
`db_root_password`, the **OVN** block (`ovn_sb_remote`, `ovn_encap_ip`), and the
**public IPv4** block (`public_interface`, `public_ip_cidr`, `public_gateway`).

Keep secrets out of git by putting them in an untracked `group_data/secrets.py`
(same variable names) or passing `--data key=value` on the command line.

## Run

```bash
pip install pyinfra            # on your workstation
cd deploy
pyinfra inventory.py deploy.py            # add --dry first to preview
```

The SSH user in `inventory.py` must be able to `sudo` (operations use `_sudo`).

## How networking is wired

* **Private (OVN).** The host runs `openvswitch-switch` + `ovn-host`
  (`ovn-controller`) only — **no `ovn-central`**. It registers as a chassis in
  your controller's Southbound DB via OVSDB `external_ids`:
  `ovn-remote=<ovn_sb_remote>`, `ovn-encap-type=geneve`,
  `ovn-encap-ip=<ovn_encap_ip>`, `system-id=<hostname>`. The OVN integration
  bridge **`br-int`** is created with `fail-mode=secure`; VM private NICs attach
  there with the app's OVN `interfaceid` (`port_uuid`). These are the
  **"config variables to connect to the controller."**
* **Public (IPv4).** A plain OVS bridge (`ovs_public_bridge`, default `ovsbr0`)
  masters the host uplink. With `manage_public_bridge = True` the deploy writes a
  netplan file (networkd, `openvswitch: {}`, `stp: false`) that enslaves
  `public_interface` and moves the host IP/route onto the bridge, then
  `netplan apply`. The same file also configures the private interface
  (`private_interface`, static `private_ip_cidr` + `private_routes`) — set
  `private_interface = ""` to leave it alone. VMs that have a public IP attach an
  OVS-bridge NIC here (libvirt `type=bridge`, `virtualport openvswitch`).
* **Kernel forwarding.** `/etc/sysctl.d/99-frappe-compute.conf` enables IP
  forwarding, proxy-ARP, loose `rp_filter`, and disables bridge netfilter.

> ⚠️ **`manage_public_bridge = True` moves the host's primary IP onto the OVS
> bridge.** If `public_interface`/addressing is wrong you can lose SSH. Verify the
> values on the box first, or set it to `False` to only create an empty bridge and
> wire the uplink yourself.

## AppArmor & libvirt

`disable_libvirt_apparmor = True` sets `security_driver = "none"` in
`/etc/libvirt/qemu.conf` and parks the libvirt AppArmor profiles in
`/etc/apparmor.d/disable`, so AppArmor never blocks qemu from `/etc/frappe-compute`
paths, OVS, or ceph. qemu also runs as the `frappe` user/group. The `frappe` user
is in the `libvirt`, `kvm`, and `openvswitch` groups so `qemu:///system` and
`ovs-vsctl` work without sudo.

## After the run — finish in the Frappe Desk

The deploy installs and starts the app but **does not** populate the
**Compute Settings** single doctype (by choice). Log into the site and fill it in:

| Compute Settings field        | value                                            |
|-------------------------------|--------------------------------------------------|
| `ovs_bridge`                  | the public bridge name (`ovs_public_bridge`, e.g. `ovsbr0`) |
| `public_ip_address`           | the host public IP (acts as VM gateway)          |
| `default_network_interface`   | the host's main interface                        |
| `orchestrator_base_url/_api_key/_api_secret` | orchestrator (control-plane) creds |
| `def_rbd_pool`, `monitor`, `ceph_mgr_*`, `libvirt_rbd_secret` | ceph, if used |

The agent's OVN/libvirt host wiring is already done by this playbook; Compute
Settings only carries the Frappe-level pointers above.

## Notes / hardening

* Runtime: bench on Frappe **`develop`**, **Python 3.14** (via uv), **Node 24**
  (via nvm, symlinked into `~/.local/bin`). All are config variables.
* Gunicorn is bound to `127.0.0.1` (only Caddy faces the network). The Frappe
  **socketio** process still listens on all interfaces — restrict ports
  **8000/9000** with your cloud security group or `ufw`, leaving **80/443/22** open.
* Process management is **supervisor** from a templated, configurable
  `/etc/supervisor/conf.d/frappe-bench.conf` (`templates/supervisor.conf.j2`; tune
  gunicorn workers/timeouts and `worker_numprocs` in `group_data/all.py`) with
  bench's own redis; there is **no nginx** — Caddy replaces it.
* Set `install_mariadb = False` to use a managed database (then point `db_host`
  at it and ensure `db_root_password` is valid there).
