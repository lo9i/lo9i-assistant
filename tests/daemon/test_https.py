"""The HTTPS listener: serves the configured certificate, and a renewed one without a restart, over HTTP/2 when the
client speaks it (daemon/http_server.py)."""

import asyncio
import ssl
from datetime import UTC, datetime, timedelta

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from assistant.core.config import settings
from assistant.daemon import https
from assistant.daemon.http_server import HttpServer, Listener


def _write_certificate(folder, name: str) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    pem = serialization.Encoding.PEM
    (folder / "key.pem").write_bytes(
        key.private_bytes(pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    (folder / "cert.pem").write_bytes(certificate.public_bytes(pem))


async def _served_name(port: int) -> str:
    context = ssl.create_default_context()
    context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
    _, writer = await asyncio.open_connection("127.0.0.1", port, ssl=context)
    der = writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
    writer.close()
    return str(x509.load_der_x509_certificate(der).subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value)


async def _app(scope, receive, send):
    if scope["type"] == "lifespan":
        return
    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def _until_listening(port: int) -> None:
    for _ in range(200):
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            await asyncio.sleep(0.02)
            continue
        writer.close()
        return
    raise AssertionError(f"Nothing listens on {port}")


def _configure(tmp_path, monkeypatch) -> None:
    configured = {"https_bind": "127.0.0.1", "https_port": 18443, "https_cert": str(tmp_path / "cert.pem")}
    for name, value in {**configured, "https_key": str(tmp_path / "key.pem")}.items():
        monkeypatch.setattr(settings, name, value)


async def test_a_renewed_certificate_is_served_without_a_restart(tmp_path, monkeypatch):
    _write_certificate(tmp_path, "first")
    _configure(tmp_path, monkeypatch)
    server, stop = HttpServer(_app, https.listener(18443)), asyncio.Event()
    tasks = [asyncio.create_task(server.serve(stop))]
    try:
        await _until_listening(18443)
        tasks.append(asyncio.create_task(https.reload_on_renewal(server)))
        assert await _served_name(18443) == "first"
        await asyncio.sleep(0.2)  # Let the watcher start before the renewal.
        _write_certificate(tmp_path, "renewed")
        for _ in range(100):
            if await _served_name(18443) == "renewed":
                break
            await asyncio.sleep(0.05)
        assert await _served_name(18443) == "renewed"
    finally:
        stop.set()
        tasks[-1].cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_https_speaks_http2_to_a_client_that_does_and_plain_http_stays_http1(tmp_path, monkeypatch):
    _write_certificate(tmp_path, "first")
    _configure(tmp_path, monkeypatch)
    stop = asyncio.Event()
    servers = [HttpServer(_app, https.listener(18443)), HttpServer(_app, Listener(host="127.0.0.1", port=18080))]
    tasks = [asyncio.create_task(s.serve(stop)) for s in servers]
    try:
        await _until_listening(18443)
        await _until_listening(18080)
        async with httpx.AsyncClient(http2=True, verify=False) as http:
            assert (await http.get("https://127.0.0.1:18443/")).http_version == "HTTP/2"
            assert (await http.get("http://127.0.0.1:18080/")).http_version == "HTTP/1.1"
    finally:
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)


def test_an_ipv6_address_is_bound_in_brackets():
    assert Listener(host="::", port=8443).address == "[::]:8443"
    assert Listener(host="0.0.0.0", port=8443).address == "0.0.0.0:8443"
    assert Listener(socket="/tmp/d.sock").address == "unix:/tmp/d.sock"


def test_https_is_off_until_a_port_is_set(monkeypatch):
    monkeypatch.setattr(settings, "https_port", 0)
    assert not https.enabled()


def test_paths_may_start_with_a_tilde(monkeypatch):
    monkeypatch.setattr(settings, "https_cert", "~/certs/cert.pem")
    assert not https.listener(8443).certfile.startswith("~")
