import socket
import subprocess
from pathlib import Path


def local_certificate_names() -> list[str]:
    host = socket.gethostname().split(".")[0] or "romini"
    names = [f"{host}.local", "127.0.0.1"]
    for address in _ipv4_addresses():
        if address not in names and not address.startswith("127."):
            names.append(address)
    return names


def ensure_local_certificate(directory: Path, *, names: list[str] | None = None) -> tuple[Path, Path] | None:
    wanted = names if names is not None else local_certificate_names()
    directory.mkdir(parents=True, exist_ok=True)
    cert = directory / "cert.pem"
    key = directory / "key.pem"
    try:
        if cert.is_file() and key.is_file() and _covers(cert, wanted):
            return cert, key
        _write_certificate(directory, cert, key, wanted)
    except (OSError, subprocess.CalledProcessError):
        return None
    return cert, key


def _ipv4_addresses() -> list[str]:
    listed = subprocess.run(["hostname", "-I"], capture_output=True, text=True)
    if listed.returncode == 0:
        return [part for part in listed.stdout.split() if ":" not in part]
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        address = probe.getsockname()[0]
    except OSError:
        return []
    finally:
        probe.close()
    return [address]


def _write_certificate(directory: Path, cert: Path, key: Path, names: list[str]) -> None:
    config = directory / "openssl.cnf"
    config.write_text(
        "\n".join(
            [
                "[req]",
                "distinguished_name = dn",
                "x509_extensions = ext",
                "prompt = no",
                "[dn]",
                f"CN = {names[0]}",
                "[ext]",
                f"subjectAltName = {','.join(_san_item(name) for name in names)}",
                "basicConstraints = CA:FALSE",
                "keyUsage = digitalSignature, keyEncipherment",
                "extendedKeyUsage = serverAuth",
                "",
            ]
        )
    )
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "825",
            "-nodes",
            "-config",
            str(config),
        ],
        check=True,
        capture_output=True,
    )
    key.chmod(0o600)
    config.unlink(missing_ok=True)


def _san_item(name: str) -> str:
    try:
        socket.inet_aton(name)
    except OSError:
        return f"DNS:{name}"
    return f"IP:{name}"


def _covers(cert: Path, names: list[str]) -> bool:
    proc = subprocess.run(
        ["openssl", "x509", "-in", str(cert), "-noout", "-ext", "subjectAltName"],
        capture_output=True,
        text=True,
        check=False,
    )
    text = proc.stdout
    return all(name in text for name in names)
