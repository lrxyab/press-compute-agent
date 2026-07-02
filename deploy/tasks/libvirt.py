"""libvirt: stop AppArmor interfering, and let the frappe user reach the sockets."""

from pyinfra import host
from pyinfra.api import deploy
from pyinfra.operations import files, server, systemd


@deploy("Setup libvirt")
def setup_libvirt():
	disable_apparmor = host.data.get("disable_libvirt_apparmor", True)

	if disable_apparmor:
		# 1. Disable the qemu security driver so AppArmor never confines a domain
		#    (qemu must reach /etc/frappe-compute/{disks,seeds,images}, OVS, ceph).
		files.line(
			name="qemu.conf: security_driver = none",
			path="/etc/libvirt/qemu.conf",
			line=r"^#?\s*security_driver\s*=.*",
			replace='security_driver = "none"',
			_sudo=True,
		)

		# 2. Park the libvirt AppArmor profiles in /etc/apparmor.d/disable so
		#    virt-aa-helper / libvirtd are not enforced either.
		server.shell(
			name="Disable libvirt AppArmor profiles",
			commands=[
				"mkdir -p /etc/apparmor.d/disable",
				"for p in usr.sbin.libvirtd usr.lib.libvirt.virt-aa-helper; do "
				"  if [ -f /etc/apparmor.d/$p ]; then "
				"    ln -sf /etc/apparmor.d/$p /etc/apparmor.d/disable/; "
				"    apparmor_parser -R /etc/apparmor.d/$p 2>/dev/null || true; "
				"  fi; "
				"done",
			],
			_sudo=True,
		)

	# 3. Make qemu run as the frappe user/group so artifacts it creates are owned
	#    consistently and reachable by the app.
	frappe_user = host.data.get("frappe_user", "frappe")
	files.line(
		name="qemu.conf: user = frappe",
		path="/etc/libvirt/qemu.conf",
		line=r"^#?\s*user\s*=.*",
		replace=f'user = "{frappe_user}"',
		_sudo=True,
	)
	files.line(
		name="qemu.conf: group = frappe",
		path="/etc/libvirt/qemu.conf",
		line=r"^#?\s*group\s*=.*",
		replace=f'group = "{frappe_user}"',
		_sudo=True,
	)

	systemd.service(
		name="Enable + restart libvirtd",
		service="libvirtd",
		running=True,
		enabled=True,
		restarted=True,
		_sudo=True,
	)

	# frappe is in the `libvirt`/`kvm` groups (users.py), so qemu:///system works.
	# `usermod` group changes only take effect in new sessions; pyinfra opens a
	# fresh login shell for the bench operations, so no extra step is needed.
