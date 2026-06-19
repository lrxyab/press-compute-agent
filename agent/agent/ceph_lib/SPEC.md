# Ceph client (`ceph_lib`)

A thin REST client for the **Ceph Manager (ceph-mgr) Dashboard API**, used for all
RBD operations when a [[disk]] or [[virtual-machine-image]] has `storage_medium =
Ceph`. One instance is bound to a single image spec `pool/name`.

File: `ceph.py`. Constructed via `Disk.ceph` (see [[disk]]) with credentials and
endpoint from Compute Settings ([[configuration-spec]]: `ceph_mgr_url`,
`ceph_mgr_username`, `ceph_mgr_password`, `ceph_api_key`).

## Auth — `__init__` `ceph.py:11-28`, `relogin` `:30-51`
Reuses the cached bearer `ceph_api_key`; if the JWT is within 120 s of expiry (or
undecodable) it re-logs into `/api/auth` and persists the new token back into Compute
Settings. All requests send the `application/vnd.ceph.api.v1.0+json` accept header and
use `verify=False` (self-signed mgr cert).

## Operations (all raise `frappe.throw` on non-2xx)
| method | lines | endpoint |
|---|---|---|
| `resize` | `:53-65` | PUT `/api/block/image/{spec}` |
| `create_disk` | `:67-85` | POST `/api/block/image` (code `17` = already-exists, ignored) |
| `create_disk_from_image` | `:87-106` | POST `…/{image}/copy` then `resize` |
| `copy_disk` | `:108-127` | POST `…/{spec}/copy` (used by Ceph snapshot capture) |
| `delete_disk` | `:129-136` | DELETE `/api/block/image/{spec}` |

Sizes are converted GiB → bytes. Note: `copy_disk` `:108-127` references an undefined
`uuid` for `dest_image_name` — latent bug on the Ceph capture path.
