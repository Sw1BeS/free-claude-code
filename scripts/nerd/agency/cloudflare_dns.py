from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TypedDict

Action = Literal["create", "update", "keep"]

PRIMARY_DOMAIN = "agency.umanoff-analytics.space"
MISSION_SUBDOMAINS = (
    "agents.umanoff-analytics.space",
    "automations.umanoff-analytics.space",
    "memory.umanoff-analytics.space",
    "obs.umanoff-analytics.space",
    "cms.umanoff-analytics.space",
)


class ExistingRecord(TypedDict, total=False):
    id: str
    type: str
    name: str
    content: str
    ttl: int
    proxied: bool


@dataclass(frozen=True)
class DNSRecordSpec:
    name: str
    type: str
    content: str
    ttl: int = 1
    proxied: bool = False

    def key(self) -> tuple[str, str]:
        return (self.type.upper(), self.name.lower())

    def payload(self) -> dict[str, object]:
        return {
            "type": self.type.upper(),
            "name": self.name,
            "content": self.content,
            "ttl": self.ttl,
            "proxied": self.proxied,
        }


@dataclass(frozen=True)
class DNSChange:
    action: Action
    record: DNSRecordSpec
    record_id: str | None = None


@dataclass(frozen=True)
class CloudflareRequest:
    method: str
    url: str
    payload: dict[str, object]


Transport = Callable[[str, str, str, dict[str, object] | None], dict[str, object]]


@dataclass(frozen=True)
class CloudflareDNSClient:
    token: str
    zone_id: str
    transport: Transport

    def apply_changes(self, changes: list[DNSChange]) -> None:
        for change in changes:
            request = cloudflare_request(self.zone_id, change)
            if request is None:
                continue
            response = self.transport(
                request.method,
                request.url,
                self.token,
                request.payload,
            )
            if response.get("success") is not True:
                msg = f"Cloudflare DNS {change.action} failed for {change.record.name}"
                raise RuntimeError(msg)


def desired_records(server_ip: str) -> list[DNSRecordSpec]:
    """Return the public DNS records for one Mission Control edge."""

    records = [
        DNSRecordSpec(
            name=PRIMARY_DOMAIN,
            type="A",
            content=server_ip,
        )
    ]
    records.extend(
        DNSRecordSpec(
            name=name,
            type="CNAME",
            content=PRIMARY_DOMAIN,
        )
        for name in MISSION_SUBDOMAINS
    )
    return records


def cloudflare_auth_headers(
    *,
    api_token: str | None = None,
    global_api_key: str | None = None,
    email: str | None = None,
) -> dict[str, str]:
    if api_token:
        return {"Authorization": f"Bearer {api_token}"}
    if global_api_key and email:
        return {
            "X-Auth-Email": email,
            "X-Auth-Key": global_api_key,
        }
    msg = "Cloudflare auth requires api_token or global_api_key with email"
    raise ValueError(msg)


def _needs_update(existing: ExistingRecord, desired: DNSRecordSpec) -> bool:
    return (
        existing.get("content") != desired.content
        or int(existing.get("ttl", 1)) != desired.ttl
        or bool(existing.get("proxied", False)) != desired.proxied
    )


def plan_changes(
    existing_records: list[ExistingRecord],
    desired: list[DNSRecordSpec],
) -> list[DNSChange]:
    """Plan create/update/keep changes without deleting unmanaged records."""

    existing_by_key = {
        (record.get("type", "").upper(), record.get("name", "").lower()): record
        for record in existing_records
    }
    changes: list[DNSChange] = []
    for record in desired:
        existing = existing_by_key.get(record.key())
        if existing is None:
            changes.append(DNSChange(action="create", record=record))
        elif _needs_update(existing, record):
            changes.append(
                DNSChange(
                    action="update",
                    record=record,
                    record_id=existing.get("id"),
                )
            )
        else:
            changes.append(
                DNSChange(
                    action="keep",
                    record=record,
                    record_id=existing.get("id"),
                )
            )
    return changes


def render_plan(plan: list[DNSChange]) -> str:
    lines = []
    for change in plan:
        record = change.record
        lines.append(
            f"{change.action.upper()} {record.type.upper()} "
            f"{record.name} -> {record.content} "
            f"ttl={record.ttl} proxied={str(record.proxied).lower()}"
        )
    return "\n".join(lines) + ("\n" if lines else "")


def cloudflare_request(
    zone_id: str,
    change: DNSChange,
) -> CloudflareRequest | None:
    base_url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    if change.action == "keep":
        return None
    if change.action == "create":
        return CloudflareRequest(
            method="POST",
            url=base_url,
            payload=change.record.payload(),
        )
    if not change.record_id:
        msg = f"Missing Cloudflare record id for update of {change.record.name}"
        raise ValueError(msg)
    return CloudflareRequest(
        method="PUT",
        url=f"{base_url}/{change.record_id}",
        payload=change.record.payload(),
    )
