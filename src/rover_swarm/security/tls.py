from __future__ import annotations

import ssl
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from rover_swarm.exceptions import ConfigurationError, SecurityError

try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    logger.warning("cryptography not installed. Advanced TLS features will be unavailable.")


@dataclass
class TlsConfig:
    cert_path: str
    key_path: str
    ca_path: Optional[str] = None
    verify_peer: bool = True
    check_hostname: bool = True
    cipher_suites: Optional[str] = None
    minimum_version: ssl.TLSVersion = ssl.TLSVersion.TLSv1_2


@dataclass
class CertificateInfo:
    subject: str
    issuer: str
    serial_number: int
    not_valid_before: datetime
    not_valid_after: datetime
    fingerprint_sha256: str
    pem_data: str
    is_ca: bool = False
    dns_names: list[str] = field(default_factory=list)
    ip_addresses: list[str] = field(default_factory=list)


class TlsManager:
    def __init__(self, config: TlsConfig) -> None:
        self.config = config
        self._server_context: Optional[ssl.SSLContext] = None
        self._client_context: Optional[ssl.SSLContext] = None
        self._cert_info: Optional[CertificateInfo] = None

        self._validate_paths()
        logger.info("TlsManager initialized with cert: {}", config.cert_path)

    def _validate_paths(self) -> None:
        if not Path(self.config.cert_path).exists():
            raise ConfigurationError(f"Certificate not found: {self.config.cert_path}")

        if not Path(self.config.key_path).exists():
            raise ConfigurationError(f"Private key not found: {self.config.key_path}")

        if self.config.ca_path and not Path(self.config.ca_path).exists():
            raise ConfigurationError(f"CA certificate not found: {self.config.ca_path}")

    def get_certificate_info(self) -> CertificateInfo:
        if self._cert_info is not None:
            return self._cert_info

        if not HAS_CRYPTOGRAPHY:
            raise ImportError("cryptography required for certificate inspection")

        with open(self.config.cert_path, "rb") as f:
            cert_data = f.read()
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())

        subject = cert.subject.rfc4514_string()
        issuer = cert.issuer.rfc4514_string()

        dns_names = []
        ip_addresses = []
        try:
            san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            for name in san.value:
                if isinstance(name, x509.DNSName):
                    dns_names.append(name.value)
                elif isinstance(name, x509.IPAddress):
                    ip_addresses.append(str(name.value))
        except x509.ExtensionNotFound:
            pass

        is_ca = False
        try:
            basic_constraints = cert.extensions.get_extension_for_class(x509.BasicConstraints)
            is_ca = basic_constraints.value.ca
        except x509.ExtensionNotFound:
            pass

        fingerprint = cert.fingerprint(hashes.SHA256())
        fingerprint_hex = ":".join(f"{b:02x}" for b in fingerprint)

        self._cert_info = CertificateInfo(
            subject=subject,
            issuer=issuer,
            serial_number=cert.serial_number,
            not_valid_before=cert.not_valid_before_utc.replace(tzinfo=timezone.utc),
            not_valid_after=cert.not_valid_after_utc.replace(tzinfo=timezone.utc),
            fingerprint_sha256=fingerprint_hex,
            pem_data=cert_data.decode("ascii"),
            is_ca=is_ca,
            dns_names=dns_names,
            ip_addresses=ip_addresses,
        )

        return self._cert_info

    def create_server_context(self, require_client_auth: bool = False) -> ssl.SSLContext:
        if self._server_context is not None:
            return self._server_context

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = self.config.minimum_version

        if self.config.cipher_suites:
            context.set_ciphers(self.config.cipher_suites)

        context.load_cert_chain(certfile=self.config.cert_path, keyfile=self.config.key_path)

        if require_client_auth:
            if not self.config.ca_path:
                raise ConfigurationError("CA certificate required for client authentication")
            context.verify_mode = ssl.CERT_REQUIRED
            context.load_verify_locations(cafile=self.config.ca_path)
        elif self.config.verify_peer:
            context.verify_mode = ssl.CERT_OPTIONAL
        else:
            context.verify_mode = ssl.CERT_NONE

        context.check_hostname = False

        context.options |= ssl.OP_NO_SSLv2
        context.options |= ssl.OP_NO_SSLv3
        context.options |= ssl.OP_NO_COMPRESSION
        context.options |= ssl.OP_SINGLE_DH_USE
        context.options |= ssl.OP_SINGLE_ECDH_USE

        self._server_context = context
        logger.debug("Created server TLS context, client_auth={}", require_client_auth)
        return context

    def create_client_context(
        self,
        server_hostname: Optional[str] = None,
        use_mtls: bool = False,
    ) -> ssl.SSLContext:
        if self._client_context is not None:
            return self._client_context

        context = ssl.create_default_context()
        context.minimum_version = self.config.minimum_version

        if self.config.cipher_suites:
            context.set_ciphers(self.config.cipher_suites)

        if use_mtls:
            context.load_cert_chain(certfile=self.config.cert_path, keyfile=self.config.key_path)

        if self.config.ca_path:
            context.load_verify_locations(cafile=self.config.ca_path)

        if self.config.verify_peer:
            context.verify_mode = ssl.CERT_REQUIRED
        else:
            context.verify_mode = ssl.CERT_NONE

        context.check_hostname = self.config.check_hostname

        context.options |= ssl.OP_NO_SSLv2
        context.options |= ssl.OP_NO_SSLv3
        context.options |= ssl.OP_NO_COMPRESSION

        self._client_context = context
        logger.debug("Created client TLS context, mTLS={}", use_mtls)
        return context

    def is_certificate_valid(self) -> tuple[bool, str]:
        try:
            info = self.get_certificate_info()
            now = datetime.now(timezone.utc)

            if now < info.not_valid_before:
                return False, "Certificate not yet valid"

            if now > info.not_valid_after:
                return False, "Certificate has expired"

            return True, "Certificate is valid"
        except Exception as e:
            return False, f"Failed to validate certificate: {e}"

    def get_days_until_expiry(self) -> int:
        info = self.get_certificate_info()
        now = datetime.now(timezone.utc)
        delta = info.not_valid_after - now
        return max(0, delta.days)


class CertificateStore:
    def __init__(self, store_path: Optional[Path] = None) -> None:
        self._store_path = store_path
        self._certificates: dict[str, CertificateInfo] = {}
        self._certificates_by_rover: dict[str, CertificateInfo] = {}

        if store_path:
            store_path.mkdir(parents=True, exist_ok=True)
            self._load_from_disk(store_path)

        logger.info("CertificateStore initialized with {} certificates", len(self._certificates))

    def _load_from_disk(self, path: Path) -> None:
        if not HAS_CRYPTOGRAPHY:
            return

        for cert_file in path.glob("*.crt"):
            try:
                with open(cert_file, "rb") as f:
                    cert_data = f.read()
                    cert = x509.load_pem_x509_certificate(cert_data, default_backend())
                    info = self._parse_certificate(cert, cert_data)

                    fingerprint = info.fingerprint_sha256
                    self._certificates[fingerprint] = info

                    rover_id = self._extract_rover_id(info)
                    if rover_id:
                        self._certificates_by_rover[rover_id] = info

            except Exception as e:
                logger.warning("Failed to load certificate {}: {}", cert_file, e)

    def _parse_certificate(self, cert: x509.Certificate, pem_data: bytes) -> CertificateInfo:
        dns_names = []
        ip_addresses = []
        try:
            san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            for name in san.value:
                if isinstance(name, x509.DNSName):
                    dns_names.append(name.value)
                elif isinstance(name, x509.IPAddress):
                    ip_addresses.append(str(name.value))
        except x509.ExtensionNotFound:
            pass

        is_ca = False
        try:
            basic_constraints = cert.extensions.get_extension_for_class(x509.BasicConstraints)
            is_ca = basic_constraints.value.ca
        except x509.ExtensionNotFound:
            pass

        fingerprint = cert.fingerprint(hashes.SHA256())
        fingerprint_hex = ":".join(f"{b:02x}" for b in fingerprint)

        return CertificateInfo(
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            serial_number=cert.serial_number,
            not_valid_before=cert.not_valid_before_utc.replace(tzinfo=timezone.utc),
            not_valid_after=cert.not_valid_after_utc.replace(tzinfo=timezone.utc),
            fingerprint_sha256=fingerprint_hex,
            pem_data=pem_data.decode("ascii"),
            is_ca=is_ca,
            dns_names=dns_names,
            ip_addresses=ip_addresses,
        )

    def _extract_rover_id(self, cert: CertificateInfo) -> Optional[str]:
        for dns_name in cert.dns_names:
            if dns_name.startswith("rover-"):
                return dns_name.split(".")[0]

        if "CN=" in cert.subject:
            cn_match = cert.subject.split("CN=")
            if len(cn_match) > 1:
                cn_value = cn_match[1].split(",")[0]
                if cn_value.startswith("rover-"):
                    return cn_value

        return None

    def add_certificate(self, pem_data: str, rover_id: Optional[str] = None) -> CertificateInfo:
        if not HAS_CRYPTOGRAPHY:
            raise ImportError("cryptography required for certificate operations")

        cert = x509.load_pem_x509_certificate(pem_data.encode("ascii"), default_backend())
        info = self._parse_certificate(cert, pem_data.encode("ascii"))

        self._certificates[info.fingerprint_sha256] = info

        actual_rover_id = rover_id or self._extract_rover_id(info)
        if actual_rover_id:
            self._certificates_by_rover[actual_rover_id] = info

        if self._store_path:
            filename = f"{info.fingerprint_sha256.replace(':', '')}.crt"
            with open(self._store_path / filename, "w") as f:
                f.write(info.pem_data)

        logger.info("Added certificate for rover: {}", actual_rover_id or "unknown")
        return info

    def get_by_fingerprint(self, fingerprint: str) -> Optional[CertificateInfo]:
        return self._certificates.get(fingerprint)

    def get_by_rover_id(self, rover_id: str) -> Optional[CertificateInfo]:
        return self._certificates_by_rover.get(rover_id)

    def remove_certificate(self, fingerprint: str) -> bool:
        if fingerprint not in self._certificates:
            return False

        cert = self._certificates.pop(fingerprint)

        for rover_id, stored in list(self._certificates_by_rover.items()):
            if stored.fingerprint_sha256 == fingerprint:
                del self._certificates_by_rover[rover_id]

        logger.info("Removed certificate: {}", fingerprint)
        return True

    def list_expired_certificates(self) -> list[CertificateInfo]:
        now = datetime.now(timezone.utc)
        return [cert for cert in self._certificates.values() if cert.not_valid_after < now]

    def list_expiring_soon(self, days: int = 30) -> list[CertificateInfo]:
        now = datetime.now(timezone.utc)
        threshold = now + timedelta(days=days)
        return [
            cert
            for cert in self._certificates.values()
            if cert.not_valid_after < threshold and cert.not_valid_after >= now
        ]


class CertGenerator:
    DEFAULT_KEY_SIZE = 4096
    DEFAULT_CERT_DAYS = 365

    def __init__(self, key_size: int = DEFAULT_KEY_SIZE) -> None:
        if not HAS_CRYPTOGRAPHY:
            raise ImportError("cryptography required for certificate generation")
        self.key_size = key_size
        logger.info("CertGenerator initialized with key_size={}", key_size)

    def generate_rsa_key(self) -> rsa.RSAPrivateKey:
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self.key_size,
            backend=default_backend(),
        )
        logger.debug("Generated RSA key")
        return key

    def create_ca_certificate(
        self,
        common_name: str = "Rover Swarm CA",
        organization: str = "Rover Swarm",
        country: str = "US",
        days: int = 3650,
    ) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
        key = self.generate_rsa_key()
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, country),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])

        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=days))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(key, hashes.SHA256(), default_backend())
        )

        logger.info("Created CA certificate: {}", common_name)
        return key, cert

    def create_rover_certificate(
        self,
        rover_id: str,
        ca_key: rsa.RSAPrivateKey,
        ca_cert: x509.Certificate,
        ip_addresses: Optional[list[str]] = None,
        dns_names: Optional[list[str]] = None,
        days: int = DEFAULT_CERT_DAYS,
    ) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
        key = self.generate_rsa_key()

        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, rover_id),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Rover Swarm"),
        ])

        san_names: list[Any] = [
            x509.DNSName(rover_id),
        ]

        if dns_names:
            for name in dns_names:
                san_names.append(x509.DNSName(name))

        if ip_addresses:
            import ipaddress
            for ip in ip_addresses:
                san_names.append(x509.IPAddress(ipaddress.ip_address(ip)))

        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=days))
            .add_extension(
                x509.SubjectAlternativeName(san_names),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=True,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([
                    x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
                    x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                ]),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256(), default_backend())
        )

        logger.info("Created rover certificate: {}", rover_id)
        return key, cert

    def key_to_pem(self, key: rsa.RSAPrivateKey, password: Optional[bytes] = None) -> bytes:
        encryption_algorithm: serialization.KeySerializationEncryption
        if password:
            encryption_algorithm = serialization.BestAvailableEncryption(password)
        else:
            encryption_algorithm = serialization.NoEncryption()

        return key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption_algorithm,
        )

    def cert_to_pem(self, cert: x509.Certificate) -> bytes:
        return cert.public_bytes(serialization.Encoding.PEM)

    def create_rover_cert_files(
        self,
        rover_id: str,
        ca_key_path: Path,
        ca_cert_path: Path,
        output_dir: Path,
        ip_addresses: Optional[list[str]] = None,
        dns_names: Optional[list[str]] = None,
        ca_key_password: Optional[bytes] = None,
        days: int = DEFAULT_CERT_DAYS,
    ) -> tuple[Path, Path]:
        with open(ca_cert_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        with open(ca_key_path, "rb") as f:
            ca_key = serialization.load_pem_private_key(
                f.read(),
                password=ca_key_password,
                backend=default_backend(),
            )

        rover_key, rover_cert = self.create_rover_certificate(
            rover_id=rover_id,
            ca_key=ca_key,
            ca_cert=ca_cert,
            ip_addresses=ip_addresses,
            dns_names=dns_names,
            days=days,
        )

        output_dir.mkdir(parents=True, exist_ok=True)

        key_path = output_dir / f"{rover_id}.key"
        cert_path = output_dir / f"{rover_id}.crt"

        with open(key_path, "wb") as f:
            f.write(self.key_to_pem(rover_key))

        with open(cert_path, "wb") as f:
            f.write(self.cert_to_pem(rover_cert))

        logger.info("Wrote rover certs: {} and {}", key_path, cert_path)
        return key_path, cert_path
