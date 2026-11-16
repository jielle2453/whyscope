"""Create a self-signed certificate so phones on the same Wi-Fi can open the hub over HTTPS.

Browsers only allow the microphone and camera on https:// pages (or on localhost). Run once:

    python scripts/make_cert.py            # writes certs/cert.pem and certs/key.pem

scripts/run.sh and scripts/run.ps1 serve HTTPS automatically when both files exist. Phones show a warning the first
time ("not private" / "not secure"); choose to continue. Re-run after the host's IP address changes.
Uses the `cryptography` package if installed, otherwise the `openssl` command (present on Ubuntu by default).
"""
import ipaddress
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "certs"
DAYS = 365


def local_ips() -> list:
    """localhost plus the address this machine uses to reach the LAN (no packet is sent)."""
    ips = {"127.0.0.1"}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ips)


def with_cryptography(ips, host, cert_path, key_path) -> bool:
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        return False
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Whyscope hub")])
    san = [x509.DNSName("localhost"), x509.DNSName(host)] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=DAYS))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .sign(key, hashes.SHA256()))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                           serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return True


def with_openssl(ips, host, cert_path, key_path) -> bool:
    exe = shutil.which("openssl")
    if not exe:
        return False
    san = ",".join(["DNS:localhost", f"DNS:{host}"] + [f"IP:{i}" for i in ips])
    with tempfile.NamedTemporaryFile("w", suffix=".cnf", delete=False) as f:
        f.write("[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\nCN=Whyscope hub\n"
                f"[ext]\nsubjectAltName={san}\n")
        cnf = f.name
    subprocess.run([exe, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", str(DAYS), "-config", cnf,
                    "-keyout", str(key_path), "-out", str(cert_path)], check=True, capture_output=True)
    Path(cnf).unlink(missing_ok=True)
    return True


def main():
    OUT.mkdir(exist_ok=True)
    cert_path, key_path = OUT / "cert.pem", OUT / "key.pem"
    ips, host = local_ips(), socket.gethostname()
    if not (with_cryptography(ips, host, cert_path, key_path) or with_openssl(ips, host, cert_path, key_path)):
        sys.exit("Need either the 'cryptography' package (pip install cryptography) or the 'openssl' command.")
    print(f"Wrote {cert_path} and {key_path}, valid {DAYS} days for: localhost, {host}, {', '.join(ips)}")
    lan = [i for i in ips if not i.startswith("127.")]
    if lan:
        port = os.environ.get("WHYSCOPE_PORT", "8000")
        print(f"On the phone (same Wi-Fi), open: https://{lan[0]}:{port}/kid  and accept the warning once.")


if __name__ == "__main__":
    main()
