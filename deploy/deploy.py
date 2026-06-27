# =============================================================================
# Frappe Compute Agent — production deploy entrypoint (Ubuntu 24.04)
# =============================================================================
# Run from this directory:
#   pyinfra inventory.py deploy.py
#
# Order matters: packages -> user -> dirs -> db -> libvirt -> networking(ovn) ->
# bench(app/site/supervisor) -> caddy.
# =============================================================================
import os
import sys

# Make the local `tasks` package importable regardless of the working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pyinfra import host
from tasks.bench import setup_bench
from tasks.caddy import setup_caddy
from tasks.config_dirs import setup_config_dirs
from tasks.database import setup_database
from tasks.libvirt import setup_libvirt
from tasks.networking import setup_networking
from tasks.packages import install_packages
from tasks.users import setup_users

# 1. OS packages + third-party apt repos (Caddy, NodeSource).
install_packages()

# 2. The `frappe` user everything runs as, its groups and sudoers.
setup_users()

# 3. /etc/frappe-compute/{disks,images,seeds,snapshots}
setup_config_dirs()

# 4. Local MariaDB (skip with install_mariadb=False to use a managed DB).
if host.data.get("install_mariadb", True):
	setup_database()

# 5. libvirt: AppArmor handling + qemu.conf + socket group access.
setup_libvirt()

# 6. OVN client (chassis) + kernel forwarding + public OVS bridge.
setup_networking()

# 7. uv + node + bench init + get-app + new-site + install-app + supervisor.
setup_bench()

# 8. Caddy reverse proxy in front of the bench.
setup_caddy()
