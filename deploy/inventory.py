# =============================================================================
# pyinfra inventory — the production host(s) to deploy the Frappe Compute Agent to.
# =============================================================================
# Each host is `("host-or-ip", {per-host data overrides})`. Per-host data wins
# over the shared defaults in `group_data/all.py`, so you can keep one config and
# only override what differs per machine (e.g. each host's OVN encap IP / public IP).
#
# Run:
#   cd deploy
#   pyinfra inventory.py deploy.py
#
# The group name is derived from the inventory variable name below ("production"),
# so `group_data/production.py` (if present) would also apply to these hosts.
# =============================================================================

production = [
	(
		"203.0.113.10",
		{
			# --- SSH connection (see pyinfra connector docs) ---
			"ssh_user": "ubuntu",
			# "ssh_key": "~/.ssh/id_ed25519",
			# "ssh_port": 22,
			# "_sudo": True,  # if the SSH user needs sudo for root operations
			# --- Per-host overrides (examples; full list in group_data/all.py) ---
			# "ovn_encap_ip": "10.0.0.11",
			# "public_interface": "eth0",
			# "public_ip_cidr": "203.0.113.10/24",
			# "public_gateway": "203.0.113.1",
		},
	),
]
