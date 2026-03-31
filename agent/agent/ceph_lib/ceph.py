import json
import time
from urllib import parse

import frappe
import jwt
import requests


class Ceph:
	def __init__(self, image_spec, ceph_api_key, ceph_mgr_password):
		self.image_spec = image_spec
		self.ceph_api_key = ceph_api_key
		self.ceph_mgr_password = ceph_mgr_password
		self.ceph_mgr_url = frappe.db.get_single_value("Compute Settings", "ceph_mgr_url")
		# if we are 2 mins before expiry or later, then regen token
		try:
			exp = jwt.decode(ceph_api_key, options={"verify_signature": False})["exp"] - 120
			if time.time() > exp:
				self.relogin()
		except Exception:
			self.relogin()

		self.headers = {
			"Authorization": f"Bearer {self.ceph_api_key}",
			"Content-Type": "application/json",
			"Accept": "application/vnd.ceph.api.v1.0+json",
		}

	def relogin(self):
		ceph_mgr_username = frappe.db.get_single_value("Compute Settings", "ceph_mgr_username")
		loginjson = {"username": ceph_mgr_username, "password": self.ceph_mgr_password}
		headers = {
			"Content-Type": "application/json",
			"Accept": "application/vnd.ceph.api.v1.0+json",
		}
		a = requests.post(
			self.ceph_mgr_url + "/api/auth",
			json=json.dumps(loginjson),
			headers=headers,
			verify=False,
		)
		if a.status_code < 200 or a.status_code >= 300:
			frappe.throw(a.text)
		else:
			try:
				token = a.json()
				frappe.db.set_value("Compute Settings", "Compute Settings", "ceph_api_key", token["token"])
				self.ceph_api_key = token["token"]
			except Exception:
				frappe.throw(a.text)

	def resize(self, size):
		resizejson = {
			"name": self.image_spec.split("/")[1],
			"size": size * 1024 * 1024 * 1024,  # GiB -> Bytes
		}
		a = requests.put(
			self.ceph_mgr_url + "/api/block/image/" + parse.quote_plus(self.image_spec),
			json=json.dumps(resizejson),
			headers=self.headers,
			verify=False,
		)
		if a.status_code < 200 or a.status_code >= 300:
			frappe.throw(a.text)

	def create_disk(self, size):
		createjson = {
			"pool_name": self.image_spec.split("/")[0],
			"name": self.image_spec.split("/")[1],
			"size": size * 1024 * 1024 * 1024,  # GiB -> Bytes
		}
		a = requests.post(
			self.ceph_mgr_url + "/api/block/image",
			json=json.dumps(createjson),
			headers=self.headers,
			verify=False,
		)
		if a.status_code < 200 or a.status_code >= 300:
			try:
				data = json.loads(a.text)
			except Exception:
				frappe.throw(a.text)
			if data["code"] != "17":
				frappe.throw(a.text)

	def create_disk_from_image(self, image, size):
		copyjson = {
			"dest_pool_name": self.image_spec.split("/")[0],
			"dest_image_name": self.image_spec.split("/")[1],
			"dest_namespace": "",  # we dont use namespaces but its a required param
		}
		a = requests.post(
			self.ceph_mgr_url + "/api/block/image/" + parse.quote_plus(image) + "/copy",
			json=json.dumps(copyjson),
			headers=self.headers,
			verify=False,
		)
		if a.status_code < 200 or a.status_code >= 300:
			try:
				data = json.loads(a.text)
			except Exception:
				frappe.throw(a.text)
			if data["code"] != "17":
				frappe.throw(a.text)
		self.resize(size)

	def copy_disk(self, dest_uuid):
		copyjson = {
			"data_pool": self.image_spec.split("/")[0],
			"dest_image_name": uuid,
			"dest_namespace": "",
			"dest_pool_name": self.image_spec.split("/")[0],
		}
		a = requests.post(
			self.ceph_mgr_url + "/api/block/image/" + parse.quote_plus(self.image_spec) + "/copy",
			json=json.dumps(copyjson),
			headers=self.headers,
			verify=False,
		)
		if a.status_code < 200 or a.status_code >= 300:
			try:
				data = json.loads(a.text)
			except Exception:
				frappe.throw(a.text)
			if data["code"] != "17":
				frappe.throw(a.text)

	def delete_disk(self):
		a = requests.delete(
			self.ceph_mgr_url + "/api/block/image/" + parse.quote_plus(self.image_spec),
			headers=self.headers,
			verify=False,
		)
		if a.status_code < 200 or a.status_code >= 300:
			frappe.throw(a.text)
