"""OS packages and third-party apt repositories (Caddy, NodeSource)."""

from pyinfra import host
from pyinfra.api import deploy
from pyinfra.operations import apt, server

# Core packages. Mirrors the reference bash script, minus ovn-central (the agent
# is an OVN *client* only) and plus the bits a non-interactive production box needs
# (mariadb, supervisor, build deps, git, cron).
BASE_PACKAGES = [
	# build / python
	"build-essential",
	"git",
	"curl",
	"pkg-config",
	"python3-dev",
	"python3-venv",
	"python3-setuptools",
	"cron",
	# frappe runtime
	"redis-server",
	"supervisor",
	"wkhtmltopdf",
	# virtualisation
	"qemu-kvm",
	"libvirt-daemon-system",
	"libvirt-clients",
	"libvirt-dev",
	"genisoimage",
	"aria2",
	# Open vSwitch + OVN *client* (NO ovn-central)
	"openvswitch-common",
	"openvswitch-switch",
	"ovn-host",
	"ovn-common",
]

# Packages needed to add the Caddy apt repo.
REPO_PREREQS = [
	"debian-keyring",
	"debian-archive-keyring",
	"apt-transport-https",
	"ca-certificates",
	"gnupg",
]


@deploy("Install packages")
def install_packages():
	db_packages = []
	if host.data.get("install_mariadb", True):
		db_packages = ["mariadb-server", "mariadb-client", "libmariadb-dev"]

	apt.update(name="apt update", _sudo=True, cache_time=3600)

	apt.packages(
		name="Install apt-repo prerequisites",
		packages=REPO_PREREQS,
		_sudo=True,
	)

	# --- Caddy stable repo (cloudsmith) ---
	server.shell(
		name="Add Caddy apt repo",
		commands=[
			"test -f /usr/share/keyrings/caddy-stable-archive-keyring.gpg || "
			"curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' "
			"| gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg",
			"test -f /etc/apt/sources.list.d/caddy-stable.list || "
			"curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' "
			"-o /etc/apt/sources.list.d/caddy-stable.list",
			"chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg "
			"/etc/apt/sources.list.d/caddy-stable.list",
		],
		_sudo=True,
	)

	# Node is installed per-user via nvm in tasks/bench.py (matches the reference
	# script), so no system nodejs/NodeSource repo here.

	apt.update(name="apt update (after adding repos)", _sudo=True)

	apt.packages(
		name="Install base + db packages",
		packages=BASE_PACKAGES + db_packages + ["caddy"],
		_sudo=True,
	)
