import http.client
import socket
import ssl
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from fastapi import FastAPI

from romini.composition.nfc import FakeNfc
from romini.fakes import FakeLed, FakePlayer, write_empty_data


def _self_signed(directory: Path) -> tuple[Path, Path]:
    key = directory / "key.pem"
    cert = directory / "cert.pem"
    config = directory / "openssl.cnf"
    config.write_text(
        "\n".join(
            [
                "[req]",
                "distinguished_name = dn",
                "x509_extensions = ext",
                "prompt = no",
                "[dn]",
                "CN = 127.0.0.1",
                "[ext]",
                "subjectAltName = IP:127.0.0.1",
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
            "2",
            "-nodes",
            "-config",
            str(config),
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


def test_dashboard_answers_https_without_redirecting_http(tmp_path: Path, monkeypatch) -> None:
    from romini.composition.dashboard import start_dashboard

    monkeypatch.setenv("ROMINI_PROFILE", "pi")
    cert, key = _self_signed(tmp_path)
    listener = start_dashboard(
        FastAPI(telemetry={"auto_configure": False}),
        host="127.0.0.1",
        port=0,
        https_port=0,
        certfile=cert,
        keyfile=key,
    )
    try:
        plain = http.client.HTTPConnection("127.0.0.1", listener.port, timeout=2)
        plain.request("GET", "/")
        plain_response = plain.getresponse()
        assert plain_response.status == 404
        assert plain_response.getheader("Location") is None

        context = ssl._create_unverified_context()
        try:
            with urlopen(f"https://127.0.0.1:{listener.https_port}/", context=context, timeout=2) as response:
                status = response.status
        except HTTPError as exc:
            status = exc.code
        assert status == 404
    finally:
        listener.close()


def test_pi_boot_serves_https_from_a_certificate_kept_beside_the_library(tmp_path: Path, monkeypatch) -> None:
    import romini.__main__ as core
    from romini.composition.provision import ROMINI_CORE_SERVICE

    data = write_empty_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "pi")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")
    monkeypatch.setenv("ROMINI_DASHBOARD_HTTPS_PORT", "0")
    monkeypatch.setattr(core, "open_ups_hat", lambda: None)
    monkeypatch.setattr(core.HostPower, "apply", lambda self, **kwargs: None)

    box = core.main(player=FakePlayer(), led=FakeLed(), nfc=FakeNfc(), ticks=[None])
    try:
        assert "ROMINI_DASHBOARD_HTTPS_PORT=443" in ROMINI_CORE_SERVICE
        https_port = box.dashboard.https_port
        assert isinstance(https_port, int) and https_port > 0
        cert = data / "tls" / "cert.pem"
        san = subprocess.check_output(
            ["openssl", "x509", "-in", str(cert), "-noout", "-ext", "subjectAltName"],
            text=True,
        )
        host = socket.gethostname().split(".")[0]
        assert f"DNS:{host}.local" in san
        context = ssl._create_unverified_context()
        try:
            with urlopen(f"https://127.0.0.1:{https_port}/", context=context, timeout=2) as response:
                status = response.status
        except HTTPError as exc:
            status = exc.code
        assert status == 200
        key = (data / "tls" / "key.pem").read_bytes()
    finally:
        box.dashboard.close()

    again = core.main(player=FakePlayer(), led=FakeLed(), nfc=FakeNfc(), ticks=[None])
    try:
        assert (data / "tls" / "key.pem").read_bytes() == key
    finally:
        again.dashboard.close()
