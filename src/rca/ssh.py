"""SSH URI parsing and SSH config management for RCA."""

from __future__ import annotations

import os
from pathlib import Path


def ssh_config_path() -> Path:
    return Path(os.environ.get("SSH_CONFIG", Path.home() / ".ssh" / "config"))


def ssh_host_exists(alias: str, config_path: Path | None = None) -> bool:
    path = config_path or ssh_config_path()
    if not path.exists():
        return False
    try:
        content = path.read_text()
    except OSError:
        return False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("host ") and alias in stripped.split()[1:]:
            return True
    return False


def append_ssh_host_block(config_path: Path, alias: str, lines: list[str]) -> None:
    if ssh_host_exists(alias, config_path):
        print(f"[SSH] Host alias '{alias}' already in {config_path}")
        return

    config_path.parent.mkdir(parents=True, exist_ok=True)
    block = "\n".join([f"Host {alias}"] + [f"  {line}" for line in lines]) + "\n"
    with config_path.open("a") as stream:
        stream.write("\n" + block)
    try:
        config_path.chmod(0o600)
    except OSError:
        pass
    print(f"[SSH] Added Host '{alias}' to {config_path}")


def parse_jumpbox_uri(jumpbox_uri: str) -> tuple[str, str, str | None]:
    """Parse ``user@host [-p port]`` into its components."""
    if not jumpbox_uri:
        raise ValueError("JUMPBOX_URI is empty")

    parts = jumpbox_uri.split()
    user_host = parts[0]
    if "@" not in user_host:
        raise ValueError(f"Invalid JUMPBOX_URI format (expected user@host): {jumpbox_uri!r}")

    user, hostname = user_host.split("@", 1)
    if not user or not hostname:
        raise ValueError(f"Invalid JUMPBOX_URI format (expected user@host): {jumpbox_uri!r}")

    port: str | None = None
    if "-p" in parts:
        port_idx = parts.index("-p")
        if port_idx + 1 < len(parts):
            port = parts[port_idx + 1]

    return user, hostname, port


def resolve_identity_file() -> str:
    for candidate in (
        os.environ.get("SSH_IDENTITY_FILE", ""),
        str(Path.home() / ".ssh" / "id_ed25519"),
        str(Path.home() / ".ssh" / "id_rsa"),
    ):
        if candidate and Path(candidate).exists():
            return candidate
    return str(Path.home() / ".ssh" / "id_ed25519")


def common_ssh_options(identity_file: str) -> list[str]:
    return [
        f"IdentityFile {identity_file}",
        "StrictHostKeyChecking no",
        "UserKnownHostsFile /dev/null",
    ]


def ensure_jumpbox_alias(
    alias: str,
    jumpbox_uri: str,
    *,
    identity_file: str | None = None,
    config_path: Path | None = None,
) -> None:
    path = config_path or ssh_config_path()
    if ssh_host_exists(alias, path):
        return
    if not jumpbox_uri:
        raise ValueError(f"Jumpbox alias '{alias}' not in SSH config and JUMPBOX_URI is unset")

    user, hostname, port = parse_jumpbox_uri(jumpbox_uri)
    identity = identity_file or resolve_identity_file()
    lines = [f"HostName {hostname}", f"User {user}", *common_ssh_options(identity)]
    if port:
        lines.insert(1, f"Port {port}")
    append_ssh_host_block(path, alias, lines)


def ensure_bastion_host(
    alias: str,
    hostname: str,
    port: int,
    user: str,
    proxy_jump: str,
    *,
    identity_file: str | None = None,
    config_path: Path | None = None,
) -> None:
    path = config_path or ssh_config_path()
    if ssh_host_exists(alias, path):
        return

    identity = identity_file or resolve_identity_file()
    lines = [
        f"HostName {hostname}",
        f"Port {port}",
        f"User {user}",
        f"ProxyJump {proxy_jump}",
        *common_ssh_options(identity),
    ]
    append_ssh_host_block(path, alias, lines)
