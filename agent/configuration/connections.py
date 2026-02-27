import libvirt


def libvirt_connection() -> libvirt.virConnect:
	return libvirt.open("qemu:///system")
