"""The `frappe` user — everything (bench, libvirt, ovs-vsctl) runs in its context."""

from pyinfra import host
from pyinfra.api import deploy
from pyinfra.operations import files, server


@deploy("Setup frappe user")
def setup_users():
	frappe_user = host.data.get("frappe_user", "frappe")
	frappe_home = host.data.get("frappe_user_home", f"/home/{frappe_user}")

	# The OVS db socket is exposed to a group so `ovs-vsctl` works as frappe
	# (the app calls /usr/bin/ovs-vsctl directly, not via sudo).
	server.group(name="Ensure openvswitch group", group="openvswitch", _sudo=True)

	server.user(
		name=f"Create {frappe_user} user",
		user=frappe_user,
		home=frappe_home,
		shell="/bin/bash",
		# libvirt + kvm => qemu:///system socket; openvswitch => ovs-vsctl;
		# sudo => the chmod sudoers rule below.
		groups=["libvirt", "kvm", "openvswitch", "sudo"],
		create_home=True,
		_sudo=True,
	)

	# The app shells out to `sudo chmod ...` (backup_lib/backup.py, reference script).
	files.put(
		name="sudoers: frappe NOPASSWD chmod",
		src="files/sudoers-frappe-compute",
		dest="/etc/sudoers.d/frappe-compute",
		mode="0440",
		_sudo=True,
	)
