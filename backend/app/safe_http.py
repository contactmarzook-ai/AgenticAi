"""Outbound HTTP for workflow steps and tools, with SSRF protection.

- Only http/https.
- Host must be on the admin allowlist ("*" allows any public host), unless the caller
  says the URL came from an admin-managed connection (`trusted_host=True`).
- Hostnames are resolved and private, loopback, link-local and metadata addresses are
  refused unless the admin enabled private networks.
- No redirects (a redirect could leave the allowlist). Response size is capped.
"""

import ipaddress
import socket
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

MAX_RESPONSE_BYTES = 1_000_000


class BlockedRequest(Exception):
    pass


def _host_allowed(host: str, allowed: list[str]) -> bool:
    host = host.lower()
    for pattern in allowed:
        p = pattern.lower().strip()
        if p == "*" or host == p or (p.startswith("*.") and host.endswith(p[1:])):
            return True
    return False


def _check_ips(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise BlockedRequest(f"Could not resolve host '{host}'") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        # Only globally routable addresses: this excludes private, loopback, link-local (cloud
        # metadata), reserved, multicast and shared/carrier-grade NAT (100.64.0.0/10) ranges.
        if not ip.is_global or ip.is_multicast:
            raise BlockedRequest(
                f"Host '{host}' resolves to a non-public address ({ip}); private networks are not allowed"
            )


SMTP_PORTS = {25, 465, 587, 2525}


def check_smtp_host(host: str, port: int, settings: dict) -> None:
    """Email servers get the same network protection as HTTP requests (security finding M3)."""
    if int(port) not in SMTP_PORTS:
        raise BlockedRequest(f"Port {port} is not an email port ({', '.join(map(str, sorted(SMTP_PORTS)))})")
    if not settings.get("allow_private_network"):
        _check_ips(host)


# Built-in destinations for chat-app connections; anything else must be on the admin allowlist.
WEBHOOK_HOSTS = {
    "slack": ["hooks.slack.com"],
    "teams": ["*.webhook.office.com", "outlook.office.com", "*.logic.azure.com", "*.powerplatform.com"],
}


def check_webhook_url(url: str, service: str, settings: dict) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise BlockedRequest("The webhook address must start with https://")
    allowed = WEBHOOK_HOSTS.get(service, []) + list(settings.get("http_allowed_hosts") or [])
    if not _host_allowed(parsed.hostname, allowed):
        raise BlockedRequest(
            f"'{parsed.hostname}' is not a {service.title()} webhook address. "
            "An administrator can allow it under Settings > Outbound HTTP."
        )


def check_url(url: str, settings: dict, trusted_host: bool = False) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise BlockedRequest("Only http:// and https:// URLs are allowed")
    if not trusted_host and not _host_allowed(parsed.hostname, settings.get("http_allowed_hosts") or []):
        raise BlockedRequest(
            f"Host '{parsed.hostname}' is not on the allowed list. An administrator can add it under Settings."
        )
    if not settings.get("allow_private_network"):
        _check_ips(parsed.hostname)


def request(
    method: str,
    url: str,
    settings: dict,
    *,
    headers: Optional[dict] = None,
    json_body: Any = None,
    content: Optional[str] = None,
    auth: Optional[tuple] = None,
    timeout: float = 30,
    trusted_host: bool = False,
) -> httpx.Response:
    check_url(url, settings, trusted_host=trusted_host)
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        with client.stream(method.upper(), url, headers=headers, json=json_body, content=content, auth=auth) as resp:
            chunks, size = [], 0
            for chunk in resp.iter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise BlockedRequest(f"Response larger than {MAX_RESPONSE_BYTES // 1000} KB")
                chunks.append(chunk)
            resp._content = b"".join(chunks)
            return resp
