"""SSRF-resistant URL resolution for external character images.

The downloader connects to a resolved, validated IP address rather than letting
the HTTP client resolve the hostname again. That pins the address for the whole
request and prevents a DNS-rebinding second lookup from redirecting the
connection to an internal service. Redirects are followed manually and every
hop is validated again.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

MAX_URL_LENGTH = 2048
ALLOWED_SCHEMES = {"http", "https"}
INTERNAL_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".intranet",
    ".lan",
    ".home",
    ".corp",
)
Resolver = Callable[[str, int], list[str]]


class UnsafeUrlError(ValueError):
    """Raised when a URL is malformed or targets a non-public destination."""


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    scheme: str
    host: str
    port: int
    ip: str
    request_target: str
    host_header: str


def system_resolver(host: str, port: int) -> list[str]:
    """Resolve a hostname to unique address strings."""
    results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses: list[str] = []
    for result in results:
        address = str(result[4][0])
        if address not in addresses:
            addresses.append(address)
    return addresses


def validate_public_ip(value: str) -> str:
    """Return a normalized public IP address or raise ``UnsafeUrlError``."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise UnsafeUrlError("The image URL resolved to an invalid address.") from exc

    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped

    if (
        not address.is_global
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise UnsafeUrlError("The image URL points to a non-public address.")
    return str(address)


def _is_internal_hostname(host: str) -> bool:
    lowered = host.rstrip(".").lower()
    if lowered == "localhost" or lowered.endswith(INTERNAL_HOST_SUFFIXES):
        return True
    # Single-label names are usually intranet hosts. Public DNS names need a dot;
    # IP literals are handled before this check.
    return "." not in lowered


def validate_and_resolve(
    url: str,
    *,
    resolver: Resolver = system_resolver,
) -> ResolvedTarget:
    """Validate an external image URL and return a pinned connection target."""
    if not isinstance(url, str) or not url.strip():
        raise UnsafeUrlError("Image URL must not be empty.")
    if len(url) > MAX_URL_LENGTH:
        raise UnsafeUrlError("Image URL is too long.")
    if any(ord(character) < 0x20 for character in url):
        raise UnsafeUrlError("Image URL contains control characters.")

    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:
        raise UnsafeUrlError("Image URL is malformed.") from exc

    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError("Only HTTP and HTTPS image URLs are allowed.")
    if parts.username is not None or parts.password is not None:
        raise UnsafeUrlError("Image URLs must not contain user credentials.")
    hostname = parts.hostname
    if not hostname:
        raise UnsafeUrlError("Image URL must include a hostname.")

    try:
        ascii_host = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise UnsafeUrlError("Image URL hostname is invalid.") from exc

    try:
        literal = ipaddress.ip_address(ascii_host)
    except ValueError:
        literal = None

    expected_port = 443 if scheme == "https" else 80
    try:
        explicit_port = parts.port
    except ValueError as exc:
        raise UnsafeUrlError("Image URL contains an invalid port.") from exc
    port = expected_port if explicit_port is None else explicit_port
    if port != expected_port:
        raise UnsafeUrlError("Image URLs may only use the standard HTTP/HTTPS port.")

    if literal is not None:
        address = validate_public_ip(str(literal))
    else:
        if _is_internal_hostname(ascii_host):
            raise UnsafeUrlError("Image URL points to an internal hostname.")
        try:
            addresses = resolver(ascii_host, port)
        except OSError as exc:
            raise UnsafeUrlError("Image URL hostname could not be resolved.") from exc
        if not addresses:
            raise UnsafeUrlError("Image URL hostname could not be resolved.")
        # Reject the whole host if any answer is internal; otherwise a hostile
        # round-robin DNS could hand one request a private address.
        for candidate in addresses:
            validate_public_ip(candidate)
        address = validate_public_ip(addresses[0])

    request_target = parts.path or "/"
    if parts.query:
        request_target = f"{request_target}?{parts.query}"

    return ResolvedTarget(
        scheme=scheme,
        host=ascii_host,
        port=port,
        ip=address,
        request_target=request_target,
        host_header=ascii_host,
    )
