"""Install bench + the agent app as the frappe user, and run it under supervisor.

Everything in the frappe-context steps runs in a login shell as the frappe user.
Node is installed via nvm (matching the reference script); node/yarn/npm are
symlinked into ~/.local/bin so they are on PATH and supervisor gets a stable path.
Python 3.14 is provided by uv (Ubuntu 24.04 only ships 3.12).
"""

import os

from pyinfra import host
from pyinfra.api import deploy
from pyinfra.operations import files, server, systemd

# Deterministic PATH (nvm + uv shims live in ~/.local/bin) and fail-fast.
_PREFIX = 'export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"; set -e; '


@deploy("Setup bench + agent app")
def setup_bench():
	frappe_user = host.data.get("frappe_user", "frappe")
	frappe_home = host.data.get("frappe_user_home", f"/home/{frappe_user}")
	bench_dir = host.data.get("bench_dir", f"{frappe_home}/frappe-bench")
	bench_name = os.path.basename(bench_dir.rstrip("/"))
	bench_bin = f"{frappe_home}/.local/bin/bench"

	python_version = host.data.get("python_version", "3.14")
	node_version = host.data.get("node_version", "24")
	frappe_branch = host.data.get("frappe_branch", "develop")

	agent_repo_url = host.data.get("agent_repo_url")
	agent_branch = host.data.get("agent_branch", "develop")
	app = host.data.get("agent_app_name", "agent")

	site_name = host.data.get("site_name")
	admin_password = host.data.get("site_admin_password")
	db_root_password = host.data.get("db_root_password")
	db_host = host.data.get("db_host", "localhost")

	webserver_port = host.data.get("webserver_port", 8000)
	socketio_port = host.data.get("socketio_port", 9000)
	compute_config_path = host.data.get("compute_config_path", "/etc/frappe-compute/")

	def frappe_shell(name, *commands):
		# bash so nvm.sh can be sourced; login shell so $HOME = the frappe home.
		server.shell(
			name=name,
			commands=[_PREFIX + c for c in commands],
			_sudo=True,
			_sudo_user=frappe_user,
			_use_sudo_login=True,
			_shell_executable="/bin/bash",
		)

	# ---- 1. nvm + node (matches the reference script) -------------------------
	frappe_shell(
		f"Install nvm + node {node_version} + yarn",
		'test -d "$HOME/.nvm" || { curl -o- '
		"https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.4/install.sh | bash; }; "
		'export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; '
		f"nvm install {node_version}; nvm alias default {node_version}; "
		"command -v yarn >/dev/null 2>&1 || npm install -g yarn; "
		'mkdir -p "$HOME/.local/bin"; '
		f'ln -sf "$(nvm which {node_version})" "$HOME/.local/bin/node"; '
		f'_nb="$(dirname "$(nvm which {node_version})")"; '
		'ln -sf "$_nb/npm" "$HOME/.local/bin/npm"; '
		'ln -sf "$_nb/yarn" "$HOME/.local/bin/yarn"',
	)

	# ---- 2. uv + python 3.14 + frappe-bench CLI -------------------------------
	frappe_shell(
		"Install uv + python + frappe-bench",
		"test -x $HOME/.local/bin/uv || curl -LsSf https://astral.sh/uv/install.sh | sh",
		f"uv python install {python_version}",
		"test -x $HOME/.local/bin/bench || uv tool install frappe-bench",
	)

	# ---- 3. bench init on the uv-managed python -------------------------------
	frappe_shell(
		"bench init",
		f"cd $HOME && test -d {bench_name}/apps/frappe || "
		f"bench init --frappe-branch {frappe_branch} "
		f'--python "$(uv python find {python_version})" {bench_name}',
	)

	# ---- 4. get the agent app -------------------------------------------------
	frappe_shell(
		f"bench get-app {app}",
		f"cd {bench_dir} && test -d apps/{app} || bench get-app {agent_repo_url} --branch {agent_branch}",
	)

	# ---- 5. create the site + install the app ---------------------------------
	frappe_shell(
		f"bench new-site {site_name}",
		f"cd {bench_dir} && test -d sites/{site_name} || "
		f"bench new-site {site_name} --no-mariadb-socket "
		f"--db-host {db_host} --db-root-username root "
		f"--db-root-password '{db_root_password}' "
		f"--admin-password '{admin_password}' --install-app {app}",
	)

	# ---- 6. bench/site config -------------------------------------------------
	frappe_shell(
		"bench config",
		f"cd {bench_dir} && bench set-config -g webserver_port {webserver_port}",
		f"cd {bench_dir} && bench set-config -g socketio_port {socketio_port}",
		f"cd {bench_dir} && bench set-config -g compute_config_path '{compute_config_path}'",
		# Serve this one site regardless of the Host header Caddy forwards.
		f"cd {bench_dir} && bench config dns_multitenant off",
		f"cd {bench_dir} && bench use {site_name}",
		f"cd {bench_dir} && bench --site {site_name} enable-scheduler",
		f"cd {bench_dir} && bench --site {site_name} set-maintenance-mode off",
	)

	# ---- 7. bench's own redis config (referenced by supervisor) ---------------
	frappe_shell(
		"bench setup redis",
		f"cd {bench_dir} && bench setup redis",
	)

	# ---- 8. supervisor program group (templated, configurable) ----------------
	files.template(
		name="Write supervisor program group",
		src="templates/supervisor.conf.j2",
		dest="/etc/supervisor/conf.d/frappe-bench.conf",
		mode="0644",
		_sudo=True,
		frappe_user=frappe_user,
		bench_dir=bench_dir,
		bench_bin=bench_bin,
		node_bin=host.data.get("node_bin", f"{frappe_home}/.local/bin/node"),
		webserver_port=webserver_port,
		gunicorn_workers=host.data.get("gunicorn_workers", 2),
		gunicorn_max_requests=host.data.get("gunicorn_max_requests", 5000),
		gunicorn_max_requests_jitter=host.data.get("gunicorn_max_requests_jitter", 500),
		gunicorn_timeout=host.data.get("gunicorn_timeout", 600),
		gunicorn_graceful_timeout=host.data.get("gunicorn_graceful_timeout", 30),
		worker_numprocs=host.data.get("worker_numprocs", 4),
	)

	server.shell(
		name="Reload supervisor program group",
		commands=[
			"supervisorctl reread",
			"supervisorctl update",
		],
		_sudo=True,
	)

	systemd.service(
		name="Enable + start supervisor",
		service="supervisor",
		running=True,
		enabled=True,
		_sudo=True,
	)
