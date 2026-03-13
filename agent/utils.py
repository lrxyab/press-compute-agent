import frappe
import jwt
from frappe.frappeclient import FrappeClient
from frappe.utils.caching import redis_cache


# returns all the information on the system about
# VMs, disks, VPCs, etc.
@frappe.whitelist(methods=["GET"])
def get_system_state():
	docs = dict()
	doctypes_to_return = ["Virtual Machine", "Disk"]
	for doctype in doctypes_to_return:
		documents = []
		document_names = frappe.get_all(doctype, pluck="name")
		for document_name in document_names:
			# the shitfuckery I have to do to get child tables
			try:
				doc = frappe.get_doc(doctype, document_name)
			except Exception:
				continue
			documents.append(doc.as_dict())
		docs[doctype] = documents
	return docs


# available memory without overprovisioning
# theoretical limit
@frappe.whitelist()
def get_free_memory():
	import psutil

	# offset by 8 to leave space
	memory_used = frappe.get_value("Virtual Machine", {}, [{"SUM": "memory"}]) or 0 + 8
	return psutil.virtual_memory().total / (1024**3) - memory_used * 1000 / 1024


def get_connection_to_orchestrator():
	compute_settings = frappe.get_single("Compute Settings")
	api_key = compute_settings.orchestrator_api_key
	api_secret = compute_settings.get_password("orchestrator_api_secret")
	base_url = compute_settings.orchestrator_base_url

	return FrappeClient(url=base_url, api_key=api_key, api_secret=api_secret)


@redis_cache(ttl=60)
def get_orchestrator_public_key() -> str:
	conn = get_connection_to_orchestrator()
	return conn.get_api("orchestrator.utils.get_public_key")


def verify_jwt(token: str, method: str):
	pub_key = get_orchestrator_public_key()
	decoded_token = jwt.decode(token, key=pub_key, algorithms=["EdDSA"])
	if decoded_token["method"] != method:
		raise frappe.throw(f"The method in the token, '{decoded_token['method']}', seems to be incorrect")
	return decoded_token


def mac_address_generator(ip_address: str):
	# Series of events:
	# 1. first 24 bits are set as 52:54 (kvm conventionally uses 52:54:00, but nothing stops us)
	# 2. remaining 32 bits can be used to perfectly fit the IP Address
	import ipaddress

	ip_address_suffix = bytearray(ipaddress.ip_address(ip_address).packed)
	mac_address_byte_array = bytearray([82, 84]) + ip_address_suffix
	return ":".join(f"{b:02x}" for b in mac_address_byte_array)


def mac_address_from_uuid(input_uuid: str | UUID):
	if isinstance(input_uuid, str):
		input_uuid = UUID(input_uuid)
	import hashlib

	h = hashlib.sha256(input_uuid.bytes).digest()
	mac = bytearray(h[:6])
	# Sets the unicast/multicast (I/G) bit to one
	mac[0] |= 0x02
	# Sets the universal/local (U/L) bit to zero
	# e.g. 0b11111110 & 0b01000101 = 0b01000100
	mac[0] &= 0xFE
	return ":".join(f"{b:02x}" for b in mac)
