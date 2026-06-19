# Snapshot & BaseSnapshot

`snapshot.py` holds two things:

1. **`BaseSnapshot`** — the shared image-capture engine, subclassed by both
   `Snapshot` (here) and [[virtual-machine-image]]. It captures a VM's disk to a
   qcow2 and (for snapshots) ships it to S3.
2. **`Snapshot`** — a point-in-time backup of a VM's root disk, stored in S3.

Files: `snapshot.py`, `snapshot.json` (schema). The `BaseSnapshot` contract is
documented inline at `snapshot.py:23-42`.

## Snapshot schema (`snapshot.json`)
Autoname `format:{uuid}`. Fields: `virtual_machine`, `file_path`, `sha256sum`,
`status` (`Draft`/`Pending`/`Available`/`Unavailable`), `progress` (Percent),
`uploaded_to_s3` (Check), `fs_freeze` (Check). `Snapshot.__init__` `:238-241`
pins `device="vda"`.

## Capture flow — `BaseSnapshot._take_image_file` `snapshot.py:56-113`
Enqueued by `take_image` `:115-124` (long queue, 5 h timeout). Steps:
1. Allocate `{CONFIG_PATH}/snapshots/{uuid}.qcow2`, mark `Pending`, commit.
2. No VM ⇒ plain copy. VM `Running` ⇒ pull a consistent copy via [[backup-engine]]
   (`VMBackup.backup_disk` + `begin`), recording `fs_freeze` and root-disk size.
   VM not running ⇒ plain `shutil.copy` of the root image.
3. Compute `sha256sum`, set progress 100, save.
4. For `Snapshot` only: `_upload_file_to_s3_and_delete_local` `:176-183` (VMIs keep
   the file locally for fast disk creation — see [[virtual-machine-image]]).

Ceph variant `_take_image_ceph` `:143-168` suspends the domain and RBD-copies
instead (no sha256).

## S3 lifecycle
- `_upload_file_to_s3` `:170-174`, `_upload_file_to_s3_and_delete_local` `:176-183`.
- `sync` `:185-196` — reconcile against S3 (`head_object`; 404 ⇒ `Unavailable`).
- `mark_unavailable` `:204-216` — delete S3 object + local file, keep the doc.
- `delete_image` `:51-54`, `_delete_from_s3` `:198-202`.

## Restore & disk creation
`create_disk_from_image` `:126-141` makes a [[disk]] from a VMI/Snapshot.
Restoring a Snapshot into a runnable disk is `create_disk_from_snapshot` in [[disk]].

## Helpers
`get_sha256sum_of_file` `:244-249`. `get_s3_client_and_credentials` `:252-259`
builds a boto3 client from orchestrator-issued AWS creds (`get_aws_credentials`,
see [[orchestrator-client]]).

HTTP wrappers (`new`/`sync`/`delete`) are in [[api-spec]].
