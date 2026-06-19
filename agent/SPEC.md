# `agent` app package

The Frappe app. Wiring, host utilities, and the entry into the doctype/api/config
layers.

## App wiring
- **`hooks.py`** — app metadata; `export_python_type_annotations = True` (the
  auto-generated `# begin: auto-generated types` blocks in every controller,
  `hooks.py:242`); and `fixtures` exporting `Virtual Machine Type` rows named `CPX%`
  (`hooks.py:244-245`). Everything else is commented Frappe boilerplate.
- **`modules.txt`** — single module `Agent`. **`patches.txt`** — no patches.
- **`templates/`, `public/`** — empty Frappe scaffolding.

## Orchestrator client & host utilities (`utils.py`)
The agent is a worker driven by a central **orchestrator** (the control plane).
This module is the client edge plus pure host helpers.
- `get_connection_to_orchestrator` `utils.py:40-46` — a `FrappeClient` built from
  Compute Settings creds (`orchestrator_api_key/secret/base_url`). Used by image
  provisioning ([[virtual-machine]]), VMI tokens ([[virtual-machine-image]]), and AWS
  creds for S3 ([[snapshot]]).
- `get_aws_credentials` `:89-91` — fetches S3 creds from the orchestrator.
- `get_orchestrator_public_key` `:49-52` (cached) + `verify_jwt` `:55-60` — validate
  EdDSA tokens the orchestrator signs (e.g. `download_vmi`).
- `mac_address_generator` `:63-71` — encodes a public IPv4 into the low 32 bits of a
  `52:54:..` MAC. `mac_address_from_uuid` `:74-86` — deterministic locally-administered
  MAC from a uuid. Both back the computed MAC properties in [[virtual-machine]].
- `get_system_state` `:11-26` (whitelisted GET) — dumps all VM + Disk docs.
  `get_free_memory` `:31-37` — psutil-based free-memory estimate.

## Sub-layers
- [[configuration-spec]] — `CONFIG_PATH`, libvirt connection, base domain XML.
- [[api-spec]] — the whitelisted REST surface the orchestrator calls.
- [[doctype-layer]] — all DocTypes (VM, Disk, Snapshot, VMI, + supporting).

## Legacy / unused
`libvirt_api.py` — an early standalone `LibvirtAPI` wrapper; imports a missing
`libvirt_python_api` package and a non-existent `CONFIG_PATH` export, so it cannot
import. Superseded by the [[virtual-machine]] controller. Safe to delete; kept only
because nothing references it.
