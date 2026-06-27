# =============================================================================
# Frappe Compute Agent — pyinfra configuration
# =============================================================================
# This is THE configuration file. Every tunable for the deploy lives here and is
# exposed to the operations as `host.data.<name>`. Override per-host or per-group
# by creating `group_data/<group>.py` or by setting host data in `inventory.py`.
#
# Anything ending in a password/secret should be moved to a private, untracked
# override file (e.g. `group_data/secrets.py`) or supplied via `--data key=value`
# on the pyinfra command line for production.
# =============================================================================

# -----------------------------------------------------------------------------
# Frappe user — EVERYTHING (bench, libvirt, ovs-vsctl) runs in this user's context
# -----------------------------------------------------------------------------
frappe_user = "frappe"
frappe_user_home = "/home/frappe"

# -----------------------------------------------------------------------------
# Bench / app
# -----------------------------------------------------------------------------
bench_dir = "/home/frappe/frappe-bench"
frappe_branch = "develop"  # Frappe framework branch for `bench init`
python_version = "3.14"  # installed via `uv python install` (24.04 only ships 3.12)
node_version = "24"  # nvm node major (matches the reference script)
# Stable path to the node binary (a symlink the nvm step creates into ~/.local/bin),
# used by the supervisor socketio program so it never hardcodes a v24.x.y path.
node_bin = "/home/frappe/.local/bin/node"

agent_repo_url = "https://github.com/frappe/press-compute-agent.git"
agent_branch = "develop"
agent_app_name = "agent"  # the app module name (`bench install-app agent`)

# -----------------------------------------------------------------------------
# Site
# -----------------------------------------------------------------------------
# The site name is the libvirt-host site AND the hostname Caddy serves / Frappe
# routes on. Keep it equal to `web_domain` (below) so the Host header matches.
site_name = "agent.localhost"
site_admin_password = "CHANGE_ME_admin_password"

# Where on-host VM artifacts live (read by the app as frappe.get_conf().compute_config_path).
compute_config_path = "/etc/frappe-compute/"

# -----------------------------------------------------------------------------
# Database (local MariaDB). Set install_mariadb=False to point at a managed DB
# (then make sure db_host/db_root_password reach a reachable server).
# -----------------------------------------------------------------------------
install_mariadb = True
db_host = "localhost"
db_root_password = "CHANGE_ME_db_root_password"

# -----------------------------------------------------------------------------
# Web tier — Caddy reverse proxy in front of the bench (no nginx)
# -----------------------------------------------------------------------------
web_domain = "agent.localhost"  # Caddy site address; real domain => automatic HTTPS
caddy_acme_email = ""  # optional ACME contact email
webserver_port = 8000  # gunicorn (bench web) bind port
socketio_port = 9000  # frappe socketio port

# -----------------------------------------------------------------------------
# Process management — templated supervisor.conf (the gunicorn knobs matter most)
# -----------------------------------------------------------------------------
gunicorn_workers = 2
gunicorn_max_requests = 5000
gunicorn_max_requests_jitter = 500
gunicorn_timeout = 600  # gunicorn -t (worker timeout)
gunicorn_graceful_timeout = 30  # must stay < stopwaitsecs to avoid orphan workers
worker_numprocs = 4  # rq worker processes per queue group

# -----------------------------------------------------------------------------
# libvirt / AppArmor
# -----------------------------------------------------------------------------
# Chosen: disable AppArmor confinement for libvirt/qemu so it never interferes
# with /etc/frappe-compute paths, OVS or ceph. Sets security_driver = "none".
disable_libvirt_apparmor = True

# -----------------------------------------------------------------------------
# OVN — private networking. The agent is ONLY an OVN client (chassis):
# openvswitch-switch + ovn-host + ovn-common. NO ovn-central here.
# ovn-controller registers this host in the controller's Southbound DB using the
# external_ids below. These are the "config variables to connect to the controller".
# -----------------------------------------------------------------------------
ovn_enabled = True
# OVN Southbound DB on the controller. Transport is plain TCP (chosen).
ovn_sb_remote = "tcp:10.50.0.1:6642"
ovn_encap_type = "geneve"
# This host's overlay/tunnel endpoint IP (its private IP, reachable by the controller).
# Keep in sync with private_ip_cidr's address below.
ovn_encap_ip = "10.50.0.3"
# Chassis id in the SB DB. Empty => use the machine hostname.
ovn_system_id = ""
# OVN integration bridge; VMs' private NICs are attached here (see app's br-int usage).
ovn_integration_bridge = "br-int"

# -----------------------------------------------------------------------------
# Public IPv4 — an OVS bridge that "masters" the host's public uplink. VMs that
# have a public IP get an OVS-bridge NIC on this bridge (see Compute Settings
# `ovs_bridge`). Chosen: fully automate — enslave the NIC and move the host IP
# onto the bridge via netplan.
#
# !!! DANGER: applying this netplan moves the host's primary IP onto the OVS
# bridge. If public_interface / addressing is wrong you can lose SSH to the box.
# Verify on the target before running, or set manage_public_bridge=False to only
# create the (empty) bridge and wire the uplink yourself.
# -----------------------------------------------------------------------------
manage_public_bridge = True
ovs_public_bridge = "ovsbr0"
public_interface = "ens10f0np0"  # physical NIC enslaved to the OVS bridge
public_ip_cidr = "103.48.90.131/24"  # host public IP in CIDR form (moves onto the bridge)
public_gateway = "103.48.90.1"
public_nameservers = ["8.8.8.8", "8.8.4.4"]

# The private / OVN-tunnel (management) interface. Configured in the same netplan
# file. Set private_interface = "" to leave the private interface untouched.
# Keep private_ip_cidr's address in sync with ovn_encap_ip above.
private_interface = "ens2"
private_ip_cidr = "10.50.0.3/16"
private_routes = [
	{"to": "10.50.0.0/16", "via": "10.50.0.1"},
]

# -----------------------------------------------------------------------------
# Kernel networking — forwarding for routed/bridged VM traffic.
# Covers IP forwarding and (proxy) ARP forwarding, plus loose rp_filter so OVN's
# asymmetric/encapsulated paths are not dropped.
# -----------------------------------------------------------------------------
configure_sysctl = True
