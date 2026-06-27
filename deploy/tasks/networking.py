"""Networking: kernel forwarding, OVS socket access, OVN client (chassis), bridges.

The agent is ONLY an OVN client. ovn-controller (from the `ovn-host` package)
registers this host as a chassis in the controller's Southbound DB using the
`external_ids` set on the local Open_vSwitch table. We never run ovn-central here.

  private NICs  -> br-int          (OVN-managed integration bridge)
  public  NICs  -> ovs_public_bridge (plain OVS bridge mastering the uplink)
"""

from pyinfra import host
from pyinfra.api import deploy
from pyinfra.operations import files, server, systemd


@deploy("Setup networking (OVN client)")
def setup_networking():
	# ---- 1. Kernel forwarding (IP forwarding + proxy/ARP forwarding) ----------
	if host.data.get("configure_sysctl", True):
		# br_netfilter must be loaded for the bridge-nf-call-* keys to exist.
		files.put(
			name="modules-load: br_netfilter",
			src="files/br_netfilter.conf",
			dest="/etc/modules-load.d/br_netfilter.conf",
			mode="0644",
			_sudo=True,
		)
		files.put(
			name="sysctl: forwarding for VM traffic",
			src="files/99-frappe-compute-sysctl.conf",
			dest="/etc/sysctl.d/99-frappe-compute.conf",
			mode="0644",
			_sudo=True,
		)
		server.shell(
			name="Load br_netfilter + apply sysctl",
			commands=[
				"modprobe br_netfilter 2>/dev/null || true",
				"sysctl --system >/dev/null",
			],
			_sudo=True,
		)

	# ---- 2. Open vSwitch up, and reachable by the frappe user -----------------
	systemd.service(
		name="Enable + start openvswitch-switch",
		service="openvswitch-switch",
		running=True,
		enabled=True,
		_sudo=True,
	)

	# Expose the OVS management socket to the `openvswitch` group (frappe is a
	# member) so the app's direct `ovs-vsctl` calls work without sudo. The socket
	# is recreated on each start, so fix it up via an ExecStartPost drop-in.
	files.put(
		name="ovsdb-server group-access drop-in",
		src="files/ovsdb-server-socket.conf",
		dest="/etc/systemd/system/ovsdb-server.service.d/10-frappe-socket.conf",
		mode="0644",
		_sudo=True,
		create_remote_dir=True,
	)
	server.shell(
		name="Reload + restart ovsdb-server for socket perms",
		commands=[
			"systemctl daemon-reload",
			"systemctl restart ovsdb-server",
			# Apply now too (in case the service was already running).
			"chgrp openvswitch /run/openvswitch/db.sock 2>/dev/null || true",
			"chmod 0660 /run/openvswitch/db.sock 2>/dev/null || true",
		],
		_sudo=True,
	)

	# ---- 3. OVN chassis config: connect this client to the controller ---------
	if host.data.get("ovn_enabled", True):
		ovn_sb_remote = host.data.get("ovn_sb_remote")
		ovn_encap_type = host.data.get("ovn_encap_type", "geneve")
		ovn_encap_ip = host.data.get("ovn_encap_ip")
		ovn_system_id = host.data.get("ovn_system_id", "") or "$(hostname)"
		br_int = host.data.get("ovn_integration_bridge", "br-int")

		server.shell(
			name="Configure OVN chassis external_ids",
			commands=[
				f'ovs-vsctl set open . external_ids:ovn-remote="{ovn_sb_remote}"',
				f'ovs-vsctl set open . external_ids:ovn-encap-type="{ovn_encap_type}"',
				f'ovs-vsctl set open . external_ids:ovn-encap-ip="{ovn_encap_ip}"',
				f'ovs-vsctl set open . external_ids:system-id="{ovn_system_id}"',
			],
			_sudo=True,
		)

		# The OVN integration bridge. ovn-controller creates it if missing, but we
		# pre-create with the canonical OVN settings to be deterministic.
		server.shell(
			name=f"Ensure OVN integration bridge {br_int}",
			commands=[
				f"ovs-vsctl --may-exist add-br {br_int} "
				f"-- set bridge {br_int} fail-mode=secure other-config:disable-in-band=true",
			],
			_sudo=True,
		)

		# ovn-controller service (unit name varies across Ubuntu builds).
		server.shell(
			name="Enable + restart ovn-controller",
			commands=[
				"systemctl enable --now ovn-host 2>/dev/null || systemctl enable --now ovn-controller",
				"systemctl restart ovn-host 2>/dev/null || systemctl restart ovn-controller",
			],
			_sudo=True,
		)

	# ---- 4. Public IPv4 OVS bridge (masters the host uplink) ------------------
	ovs_public_bridge = host.data.get("ovs_public_bridge", "br-ex")

	if host.data.get("manage_public_bridge", False):
		# !!! Moves the host IP onto the OVS bridge — can drop SSH if misconfigured.
		files.template(
			name=f"netplan: OVS public bridge {ovs_public_bridge}",
			src="templates/ovs-public.netplan.yaml.j2",
			dest="/etc/netplan/99-frappe-ovs-public.yaml",
			mode="0600",
			_sudo=True,
			ovs_public_bridge=ovs_public_bridge,
			public_interface=host.data.get("public_interface"),
			public_ip_cidr=host.data.get("public_ip_cidr"),
			public_gateway=host.data.get("public_gateway"),
			public_nameservers=host.data.get("public_nameservers", []),
			private_interface=host.data.get("private_interface", ""),
			private_ip_cidr=host.data.get("private_ip_cidr", ""),
			private_routes=host.data.get("private_routes", []),
		)
		server.shell(
			name="netplan apply (public OVS bridge)",
			commands=["netplan apply"],
			_sudo=True,
		)
	else:
		# Just create an empty bridge; operator wires the uplink later.
		server.shell(
			name=f"Ensure empty OVS public bridge {ovs_public_bridge}",
			commands=[f"ovs-vsctl --may-exist add-br {ovs_public_bridge}"],
			_sudo=True,
		)
