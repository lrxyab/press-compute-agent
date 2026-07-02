"""On-host artifact directories under CONFIG_PATH (/etc/frappe-compute/)."""

from pyinfra import host
from pyinfra.api import deploy
from pyinfra.operations import files

# Subdirectories the app reads/writes (see agent/configuration/paths.py).
SUBDIRS = ["disks", "images", "seeds", "snapshots"]


@deploy("Setup config directories")
def setup_config_dirs():
	frappe_user = host.data.get("frappe_user", "frappe")
	config_path = host.data.get("compute_config_path", "/etc/frappe-compute/").rstrip("/")

	files.directory(
		name=f"Create {config_path}",
		path=config_path,
		present=True,
		user=frappe_user,
		group=frappe_user,
		mode="0755",
		_sudo=True,
	)

	for sub in SUBDIRS:
		files.directory(
			name=f"Create {config_path}/{sub}",
			path=f"{config_path}/{sub}",
			present=True,
			user=frappe_user,
			group=frappe_user,
			mode="0755",
			_sudo=True,
		)
