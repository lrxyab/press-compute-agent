import json
from urllib import parse

import frappe
import requests
from frappe.utils.password import get_decrypted_password


class Ceph:
	def __init__(self, image_spec):
		self.image_spec = image_spec
		self.ceph_api_key = get_decrypted_password("Compute Settings", "Compute Settings", "ceph_api_key")
		self.ceph_mgr_url = frappe.db.get_single_value("Compute Settings", "ceph_mgr_url")
		self.headers = {
			"Authorization": f"Bearer {self.ceph_api_key}",
			"Content-Type": "application/json",
			"Accept": "application/vnd.ceph.api.v1.0+json",
		}

	def resize(self, size):
		resizejson = {
			"name": self.get_path().split("/")[1],
			"size": size * 1024 * 1024 * 1024,  # GiB -> Bytes
		}
		requests.put(
			self.ceph_mgr_url + "/api/block/image/" + parse.quote_plus(self.image_spec),
			json=json.dumps(resizejson),
			headers=headers,
			verify=False,
		)

	def create_disk(self, size):
		createjson = {
			"pool_name": self.image_spec.split("/")[0],
			"name": self.image_spec.split("/")[1],
			"size": size * 1024 * 1024 * 1024,  # GiB -> Bytes
		}
		# %2F is encoding for the / character
		requests.post(
			self.ceph_mgr_url + "/api/block/image", json=json.dumps(createjson), headers=headers, verify=False
		)

	def create_disk_from_image(self, image, size):
		copyjson = {
			"dest_pool_name": self.image_spec.split("/")[0],
			"dest_image_name": self.image_spec.split("/")[1],
			"dest_namespace": "",  # we dont use namespaces but its a required param
		}
		# %2F is encoding for the / character
		requests.post(
			self.ceph_mgr_url + "/api/block/image/" + parse.quote_plus(image) + "/copy",
			json=json.dumps(copyjson),
			headers=headers,
			verify=False,
		)
		self.set_disk_size(size)

	def delete_disk(self):
		requests.delete(
			self.ceph_mgr_url + "/api/block/image/" + parse.quote_plus(image_spec),
			headers=headers,
			verify=False,
		)
