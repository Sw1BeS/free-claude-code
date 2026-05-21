import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DNS_PATH = ROOT / "scripts" / "nerd" / "agency" / "cloudflare_dns.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or not isinstance(spec.loader, SourceFileLoader):
        raise AssertionError(f"Unable to load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_desired_records_routes_subdomains_to_single_mission_control_edge():
    dns = load_module("agency_cloudflare_dns_desired", DNS_PATH)

    records = dns.desired_records("65.108.9.96")
    by_name = {record.name: record for record in records}

    assert by_name["agency.umanoff-analytics.space"].type == "A"
    assert by_name["agency.umanoff-analytics.space"].content == "65.108.9.96"
    assert by_name["agency.umanoff-analytics.space"].proxied is False
    assert by_name["memory.umanoff-analytics.space"].type == "CNAME"
    assert (
        by_name["memory.umanoff-analytics.space"].content
        == "agency.umanoff-analytics.space"
    )
    assert {
        "agency.umanoff-analytics.space",
        "agents.umanoff-analytics.space",
        "automations.umanoff-analytics.space",
        "memory.umanoff-analytics.space",
        "obs.umanoff-analytics.space",
        "cms.umanoff-analytics.space",
    }.issubset(by_name)


def test_plan_changes_upserts_expected_records_without_deleting_unmanaged_records():
    dns = load_module("agency_cloudflare_dns_plan", DNS_PATH)
    desired = dns.desired_records("65.108.9.96")
    existing = [
        {
            "id": "agency-old",
            "type": "A",
            "name": "agency.umanoff-analytics.space",
            "content": "203.0.113.10",
            "ttl": 1,
            "proxied": False,
        },
        {
            "id": "agents-ok",
            "type": "CNAME",
            "name": "agents.umanoff-analytics.space",
            "content": "agency.umanoff-analytics.space",
            "ttl": 1,
            "proxied": False,
        },
        {
            "id": "legacy",
            "type": "A",
            "name": "cmd.umanoff-analytics.space",
            "content": "64.23.234.242",
            "ttl": 1,
            "proxied": False,
        },
    ]

    plan = dns.plan_changes(existing, desired)
    actions = {(change.action, change.record.name) for change in plan}

    assert ("update", "agency.umanoff-analytics.space") in actions
    assert ("keep", "agents.umanoff-analytics.space") in actions
    assert ("create", "memory.umanoff-analytics.space") in actions
    assert all(change.record.name != "cmd.umanoff-analytics.space" for change in plan)
    assert {change.action for change in plan}.issubset({"create", "update", "keep"})


def test_render_plan_summarizes_changes_without_secret_material():
    dns = load_module("agency_cloudflare_dns_render", DNS_PATH)
    plan = [
        dns.DNSChange(
            action="create",
            record=dns.DNSRecordSpec(
                name="memory.umanoff-analytics.space",
                type="CNAME",
                content="agency.umanoff-analytics.space",
            ),
        ),
        dns.DNSChange(
            action="keep",
            record=dns.DNSRecordSpec(
                name="agents.umanoff-analytics.space",
                type="CNAME",
                content="agency.umanoff-analytics.space",
            ),
            record_id="record-id",
        ),
    ]

    text = dns.render_plan(plan)

    assert (
        "CREATE CNAME memory.umanoff-analytics.space -> agency.umanoff-analytics.space"
        in text
    )
    assert (
        "KEEP CNAME agents.umanoff-analytics.space -> agency.umanoff-analytics.space"
        in text
    )
    assert "record-id" not in text


def test_cloudflare_request_uses_zone_scoped_upserts_only():
    dns = load_module("agency_cloudflare_dns_request", DNS_PATH)
    create = dns.DNSChange(
        action="create",
        record=dns.DNSRecordSpec(
            name="memory.umanoff-analytics.space",
            type="CNAME",
            content="agency.umanoff-analytics.space",
        ),
    )
    update = dns.DNSChange(
        action="update",
        record=dns.DNSRecordSpec(
            name="agency.umanoff-analytics.space",
            type="A",
            content="65.108.9.96",
        ),
        record_id="agency-record",
    )
    keep = dns.DNSChange(action="keep", record=create.record, record_id="memory-record")

    create_request = dns.cloudflare_request("zone-id", create)
    update_request = dns.cloudflare_request("zone-id", update)

    assert create_request.method == "POST"
    assert (
        create_request.url
        == "https://api.cloudflare.com/client/v4/zones/zone-id/dns_records"
    )
    assert create_request.payload["name"] == "memory.umanoff-analytics.space"
    assert update_request.method == "PUT"
    assert update_request.url.endswith("/dns_records/agency-record")
    assert dns.cloudflare_request("zone-id", keep) is None


def test_client_apply_changes_skips_keep_and_sends_upserts_through_transport():
    dns = load_module("agency_cloudflare_dns_client", DNS_PATH)
    calls = []

    def transport(method, url, token, payload=None):
        calls.append((method, url, token, payload))
        return {"success": True, "result": {"id": "created"}}

    client = dns.CloudflareDNSClient(
        token="token-value",
        zone_id="zone-id",
        transport=transport,
    )
    client.apply_changes(
        [
            dns.DNSChange(
                action="keep",
                record=dns.DNSRecordSpec(
                    name="agents.umanoff-analytics.space",
                    type="CNAME",
                    content="agency.umanoff-analytics.space",
                ),
                record_id="agents",
            ),
            dns.DNSChange(
                action="create",
                record=dns.DNSRecordSpec(
                    name="memory.umanoff-analytics.space",
                    type="CNAME",
                    content="agency.umanoff-analytics.space",
                ),
            ),
        ]
    )

    assert len(calls) == 1
    assert calls[0][0] == "POST"
    assert calls[0][2] == "token-value"
    assert calls[0][3]["name"] == "memory.umanoff-analytics.space"


def test_cloudflare_auth_headers_support_scoped_token_and_global_key():
    dns = load_module("agency_cloudflare_dns_auth", DNS_PATH)

    token_headers = dns.cloudflare_auth_headers(api_token="token-value")
    global_headers = dns.cloudflare_auth_headers(
        global_api_key="global-key",
        email="owner@example.com",
    )

    assert token_headers == {"Authorization": "Bearer token-value"}
    assert global_headers == {
        "X-Auth-Email": "owner@example.com",
        "X-Auth-Key": "global-key",
    }
