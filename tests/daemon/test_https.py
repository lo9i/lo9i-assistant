"""The HTTPS listener: serves the configured certificate, and a renewed one without a restart."""

import asyncio
import ssl
from datetime import UTC, datetime, timedelta

import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from assistant.core.config import settings
from assistant.daemon import https


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
    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def test_a_renewed_certificate_is_served_without_a_restart(tmp_path, monkeypatch):
    _write_certificate(tmp_path, "first")
    configured = {"https_bind": "127.0.0.1", "https_port": 18443, "https_cert": str(tmp_path / "cert.pem")}
    for name, value in {**configured, "https_key": str(tmp_path / "key.pem")}.items():
        monkeypatch.setattr(settings, name, value)
    server = uvicorn.Server(uvicorn.Config(_app, lifespan="off", log_level="warning", **https.bind()))
    tasks = [asyncio.create_task(server.serve())]
    try:
        while not server.started:
            await asyncio.sleep(0.01)
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
        server.should_exit = True
        tasks[-1].cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def test_https_is_off_until_a_port_is_set(monkeypatch):
    monkeypatch.setattr(settings, "https_port", 0)
    assert not https.enabled()


def test_paths_may_start_with_a_tilde(monkeypatch):
    monkeypatch.setattr(settings, "https_cert", "~/certs/cert.pem")
    assert not https.bind()["ssl_certfile"].startswith("~")
