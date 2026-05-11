import subprocess
import time
from functools import cached_property
from typing import TYPE_CHECKING
from xml.dom.minidom import Document

import frappe

if TYPE_CHECKING:
	import libvirt


class VMBackup:
	def __init__(self, domain: libvirt.virDomain, image_id: str | None = None, doctype: str | None = None):
		self.domain = domain
		self.image_id = image_id
		self.doctype = doctype

	def backup_disk(self, disk_device, destination):
		xml = Document()

		domainbackup = xml.createElement("domainbackup")
		domainbackup.setAttribute("mode", "push")
		xml.appendChild(domainbackup)

		disks = xml.createElement("disks")
		domainbackup.appendChild(disks)

		disk = xml.createElement("disk")
		disk.setAttribute("name", disk_device)
		disk.setAttribute("type", "file")
		disks.appendChild(disk)

		target = xml.createElement("target")
		target.setAttribute("file", destination)
		disk.appendChild(target)

		self.disk_device = disk_device
		self.destination = destination
		self.xml = xml.toxml()

	def begin(self):
		if self.host_has_qemu_ga:
			self.domain.fsFreeze()

		self.domain.backupBegin(self.xml, None, 0)

		if self.host_has_qemu_ga:
			self.domain.fsThaw()

		while True:
			progress, completed = self.get_status()
			if self.image_id:
				if completed:
					percent_progress = 100
				else:
					percent_progress = progress * 100
				if self.doctype:
					frappe.db.set_value(
						self.doctype,
						self.image_id,
						"progress",
						percent_progress,
						update_modified=False,
					)
				frappe.db.commit()
			if completed:
				break
			time.sleep(0.3)

		# add `<your_user> ALL=\(ALL\) NOPASSWD: /user/bin/chmod` to /etc/sudoers
		subprocess.call(["sudo", "chmod", "777", self.destination])

	def get_status(self):
		info = self.domain.blockJobInfo(self.disk_device, 0)

		if "cur" not in info:
			return 1, True
		if info["cur"] == info["end"]:
			return 1, True
		return info["cur"] / info["end"], False

	@cached_property
	def host_has_qemu_ga(self):
		try:
			self.domain.guestInfo()
		except Exception:
			return False
		return True
