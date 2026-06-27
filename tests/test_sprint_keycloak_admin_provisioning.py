from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.capability_execution_service import CapabilityExecutionService
from services.capability_registry_service import CapabilityRegistryService
from services.keycloak_admin_service import KeycloakAdminService
from services.keycloak_provisioning_service import KeycloakProvisioningService
from models.capability_request import CapabilityRequest


class FakeResponse:
    def __init__(self, status_code: int, payload: Any = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self) -> Any:
        return self._payload


class FakeKeycloak:
    """Minimal in-memory stand-in for the Keycloak Admin REST API."""

    def __init__(self) -> None:
        self.realms: dict[str, dict[str, Any]] = {}
        self.scopes: dict[str, dict[str, Any]] = {}
        self.clients: dict[str, dict[str, Any]] = {}
        self.default_scopes: dict[str, set[str]] = {}
        self.protocol_mappers: dict[str, dict[str, dict[str, Any]]] = {}
        self.components: dict[str, dict[str, dict[str, Any]]] = {}
        self.realm_optional_scopes: dict[str, set[str]] = {}
        self._next_id = 1

    def _new_id(self, prefix: str) -> str:
        self._next_id += 1
        return f"{prefix}-{self._next_id}"

    def token(self, *args: Any, **kwargs: Any) -> FakeResponse:
        return FakeResponse(200, {"access_token": "fake-admin-token", "expires_in": 300})

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        path = url.split("/admin/realms", 1)[1]
        if method == "GET" and path == "":
            return FakeResponse(404)
        if method == "POST" and path == "":
            realm = kwargs["json"]["realm"]
            self.realms[realm] = {**kwargs["json"], "id": self._new_id("realm")}
            return FakeResponse(201)
        if method == "GET" and path.count("/") == 1:
            realm = path.split("/")[1]
            return FakeResponse(200, self.realms[realm]) if realm in self.realms else FakeResponse(404)

        if path.endswith("/client-scopes") and method == "GET":
            realm = path.split("/")[1]
            return FakeResponse(200, list(self.scopes.get(realm, {}).values()))
        if path.endswith("/client-scopes") and method == "POST":
            realm = path.split("/")[1]
            name = kwargs["json"]["name"]
            scope_id = self._new_id("scope")
            self.scopes.setdefault(realm, {})[name] = {"id": scope_id, "name": name}
            return FakeResponse(201)

        if path.endswith("/clients") and method == "GET":
            realm = path.split("/")[1]
            client_id = kwargs.get("params", {}).get("clientId")
            client = self.clients.get(realm, {}).get(client_id)
            return FakeResponse(200, [client] if client else [])
        if path.endswith("/clients") and method == "POST":
            realm = path.split("/")[1]
            client_id = kwargs["json"]["clientId"]
            uuid = self._new_id("client")
            self.clients.setdefault(realm, {})[client_id] = {**kwargs["json"], "id": uuid}
            self.default_scopes[uuid] = set()
            return FakeResponse(201)

        if "/clients/" in path and "/" not in path.split("/clients/")[1] and method == "PUT":
            realm = path.split("/")[1]
            uuid = path.split("/clients/")[1]
            payload = kwargs["json"]
            for client_id, client in self.clients.get(realm, {}).items():
                if client["id"] == uuid:
                    client.update(payload)
                    return FakeResponse(204)
            return FakeResponse(404)

        if "/client-secret" in path and method == "GET":
            uuid = path.split("/clients/")[1].split("/client-secret")[0]
            return FakeResponse(200, {"type": "secret", "value": f"secret-for-{uuid}"})

        if "/default-client-scopes/" in path and method == "PUT":
            uuid = path.split("/clients/")[1].split("/default-client-scopes/")[0]
            scope_id = path.rsplit("/", 1)[1]
            self.default_scopes.setdefault(uuid, set()).add(scope_id)
            return FakeResponse(204)

        if "/default-optional-client-scopes/" in path and method == "PUT":
            realm = path.split("/")[1]
            scope_id = path.rsplit("/", 1)[1]
            self.realm_optional_scopes.setdefault(realm, set()).add(scope_id)
            return FakeResponse(204)

        if path.endswith("/components") and method == "GET":
            realm = path.split("/")[1]
            params = kwargs.get("params", {})
            items = list(self.components.get(realm, {}).values())
            if "parent" in params:
                items = [c for c in items if c.get("parentId") == params["parent"]]
            if "type" in params:
                items = [c for c in items if c.get("providerType") == params["type"]]
            return FakeResponse(200, items)
        if path.endswith("/components") and method == "POST":
            realm = path.split("/")[1]
            component_id = self._new_id("component")
            self.components.setdefault(realm, {})[component_id] = {**kwargs["json"], "id": component_id}
            return FakeResponse(201)
        if "/components/" in path and method == "PUT":
            realm = path.split("/")[1]
            component_id = path.rsplit("/", 1)[1]
            if component_id not in self.components.get(realm, {}):
                return FakeResponse(404)
            self.components[realm][component_id].update(kwargs["json"])
            return FakeResponse(204)

        if path.endswith("/protocol-mappers/models") and method == "GET":
            uuid = path.split("/clients/")[1].split("/protocol-mappers/models")[0]
            return FakeResponse(200, list(self.protocol_mappers.get(uuid, {}).values()))
        if path.endswith("/protocol-mappers/models") and method == "POST":
            uuid = path.split("/clients/")[1].split("/protocol-mappers/models")[0]
            name = kwargs["json"]["name"]
            mapper_id = self._new_id("mapper")
            self.protocol_mappers.setdefault(uuid, {})[name] = {"id": mapper_id, **kwargs["json"]}
            return FakeResponse(201)
        if "/protocol-mappers/models/" in path and method == "PUT":
            uuid = path.split("/clients/")[1].split("/protocol-mappers/models/")[0]
            mapper_id = path.rsplit("/", 1)[1]
            payload = kwargs["json"]
            for mapper in self.protocol_mappers.get(uuid, {}).values():
                if mapper["id"] == mapper_id:
                    mapper.update(payload)
                    return FakeResponse(204)
            return FakeResponse(404)

        raise AssertionError(f"unhandled fake keycloak call: {method} {path}")


def _admin(monkeypatch, fake: FakeKeycloak) -> KeycloakAdminService:
    monkeypatch.setattr("services.keycloak_admin_service.requests.post", fake.token)
    monkeypatch.setattr("services.keycloak_admin_service.requests.request", fake.request)
    return KeycloakAdminService(admin_username="admin", admin_password="admin")


def test_ensure_client_and_default_scopes_are_idempotent(monkeypatch):
    fake = FakeKeycloak()
    admin = _admin(monkeypatch, fake)

    admin.ensure_realm()
    admin.ensure_realm()
    assert list(fake.realms.keys()) == ["ageix"]

    first = admin.ensure_client("ageix-mcp-chatgpt")
    second = admin.ensure_client("ageix-mcp-chatgpt")
    assert first["id"] == second["id"]

    admin.set_default_client_scopes(first["id"], ["ageix.capability:ageix.health", "ageix.project:Ageix"])
    admin.set_default_client_scopes(first["id"], ["ageix.capability:ageix.health"])
    assert len(fake.default_scopes[first["id"]]) == 2


def test_provision_client_persists_secret_outside_git_tracked_config(tmp_path: Path, monkeypatch):
    fake = FakeKeycloak()
    admin = _admin(monkeypatch, fake)

    auth_config_path = tmp_path / ".ageix" / "config" / "auth.json"
    auth_config_path.parent.mkdir(parents=True)
    auth_config_path.write_text(json.dumps({
        "jwt": {
            "default_allowed_capabilities": ["*"],
            "default_allowed_projects": ["Ageix_Test"],
        },
    }), encoding="utf-8")

    service = KeycloakProvisioningService(tmp_path, admin=admin)
    result = service.provision_client("chatgpt")

    assert result.skipped is False
    assert result.keycloak_client_id == "ageix-mcp-chatgpt"
    assert any(name.startswith("ageix.capability:") for name in result.scope_names)
    assert any(name.startswith("ageix.project:Ageix_Test") for name in result.scope_names)

    secret_path = tmp_path / ".ageix" / "instance" / "keycloak" / "chatgpt.json"
    assert secret_path.exists()
    persisted = json.loads(secret_path.read_text(encoding="utf-8"))
    assert persisted["client_secret"].startswith("secret-for-")
    assert result.secret_path == str(secret_path)


def test_provision_client_attaches_distinct_agent_id_claim_per_client(tmp_path: Path, monkeypatch):
    fake = FakeKeycloak()
    admin = _admin(monkeypatch, fake)

    auth_config_path = tmp_path / ".ageix" / "config" / "auth.json"
    auth_config_path.parent.mkdir(parents=True)
    auth_config_path.write_text(json.dumps({
        "jwt": {
            "default_allowed_capabilities": ["*"],
            "default_allowed_projects": ["Ageix_Test"],
        },
    }), encoding="utf-8")

    service = KeycloakProvisioningService(tmp_path, admin=admin)
    chatgpt_result = service.provision_client("chatgpt")
    claude_result = service.provision_client("claude")

    assert chatgpt_result.agent_id == "lex"
    assert claude_result.agent_id == "claude"

    chatgpt_uuid = fake.clients["ageix"]["ageix-mcp-chatgpt"]["id"]
    claude_uuid = fake.clients["ageix"]["ageix-mcp-claude"]["id"]
    assert fake.protocol_mappers[chatgpt_uuid]["hardcoded-agent_id"]["config"]["claim.value"] == "lex"
    assert fake.protocol_mappers[claude_uuid]["hardcoded-agent_id"]["config"]["claim.value"] == "claude"

    second = service.provision_client("claude")
    assert len(fake.protocol_mappers[claude_uuid]) == 1
    assert second.agent_id == "claude"


def test_provision_client_skips_placeholder_clients(tmp_path: Path, monkeypatch):
    fake = FakeKeycloak()
    admin = _admin(monkeypatch, fake)
    (tmp_path / ".ageix" / "config").mkdir(parents=True)

    service = KeycloakProvisioningService(tmp_path, admin=admin)
    result = service.provision_client("gemini")

    assert result.skipped is True
    assert result.reason == "mcp_client_disabled_or_placeholder"


def test_keycloak_reconcile_capability_requires_chair_agent(tmp_path: Path, monkeypatch):
    fake = FakeKeycloak()
    _admin(monkeypatch, fake)
    monkeypatch.setattr(
        "services.capabilities.identity_provisioning_capabilities.KeycloakProvisioningService",
        lambda repo_root: KeycloakProvisioningService(repo_root, admin=KeycloakAdminService(admin_username="admin", admin_password="admin")),
    )
    (tmp_path / ".ageix" / "config").mkdir(parents=True)
    (tmp_path / ".ageix" / "config" / "auth.json").write_text(json.dumps({
        "jwt": {"default_allowed_capabilities": ["*"], "default_allowed_projects": []},
    }), encoding="utf-8")

    execution = CapabilityExecutionService(tmp_path)

    denied = execution.execute(CapabilityRequest(
        capability_id="identity.keycloak.reconcile",
        session_id="kc-test",
        agent_id="lex",
        arguments={},
    ))
    assert denied.success is False
    assert denied.error == "capability_not_exposed_to_external_agents"

    allowed = execution.execute(CapabilityRequest(
        capability_id="identity.keycloak.reconcile",
        session_id="kc-test",
        agent_id="chair",
        arguments={},
    ))
    assert allowed.success is True
    assert allowed.result["clients"]


def test_keycloak_capabilities_are_discovered_but_not_externally_exposed(tmp_path: Path):
    capability_ids = {cap.capability_id for cap in CapabilityRegistryService(tmp_path).list_capabilities()}
    assert "identity.keycloak.reconcile" in capability_ids
    assert "identity.keycloak.client.provision" in capability_ids
    assert "identity.keycloak.connector.provision" in capability_ids
    assert "identity.keycloak.connector.enable_self_registration" in capability_ids


def test_ensure_trusted_hosts_policy_creates_and_is_idempotent(monkeypatch):
    fake = FakeKeycloak()
    admin = _admin(monkeypatch, fake)
    admin.ensure_realm()

    first = admin.ensure_trusted_hosts_policy(["claude.ai"])
    second = admin.ensure_trusted_hosts_policy(["claude.ai"])

    assert first["id"] == second["id"]
    stored = fake.components["ageix"][first["id"]]
    assert stored["providerId"] == "trusted-hosts"
    assert stored["config"]["trusted-hosts"] == ["claude.ai"]
    assert stored["config"]["client-uris-must-match"] == ["true"]
    assert stored["config"]["host-sending-registration-request-must-match"] == ["false"]


def test_ensure_trusted_hosts_policy_updates_existing(monkeypatch):
    fake = FakeKeycloak()
    admin = _admin(monkeypatch, fake)
    admin.ensure_realm()

    admin.ensure_trusted_hosts_policy(["claude.ai"])
    updated = admin.ensure_trusted_hosts_policy(["claude.ai", "other.example.com"])

    assert updated["config"]["trusted-hosts"] == ["claude.ai", "other.example.com"]
    assert len(fake.components["ageix"]) == 1


def test_ensure_consent_required_and_max_clients_policies_are_idempotent(monkeypatch):
    fake = FakeKeycloak()
    admin = _admin(monkeypatch, fake)
    admin.ensure_realm()

    admin.ensure_consent_required_policy()
    admin.ensure_consent_required_policy()
    admin.ensure_max_clients_policy(1)
    admin.ensure_max_clients_policy(1)

    components = fake.components["ageix"]
    assert sum(1 for c in components.values() if c["providerId"] == "consent-required") == 1
    assert sum(1 for c in components.values() if c["providerId"] == "max-clients") == 1
    assert next(c for c in components.values() if c["providerId"] == "max-clients")["config"]["max-clients"] == ["1"]


def test_enable_connector_self_registration_configures_policies_and_optional_scopes(tmp_path: Path, monkeypatch):
    fake = FakeKeycloak()
    admin = _admin(monkeypatch, fake)

    auth_config_path = tmp_path / ".ageix" / "config" / "auth.json"
    auth_config_path.parent.mkdir(parents=True)
    auth_config_path.write_text(json.dumps({
        "jwt": {
            "default_allowed_capabilities": ["*"],
            "default_allowed_projects": ["Ageix_Test"],
        },
    }), encoding="utf-8")

    service = KeycloakProvisioningService(tmp_path, admin=admin)
    result = service.enable_connector_self_registration(["claude.ai"], max_clients=1)

    assert result["policies"]["trusted_hosts_policy"]["config"]["trusted-hosts"] == ["claude.ai"]
    assert result["policies"]["consent_required_policy"]["providerId"] == "consent-required"
    assert result["policies"]["max_clients_policy"]["config"]["max-clients"] == ["1"]
    assert any(name.startswith("ageix.capability:") for name in result["optional_scope_names"])
    assert any(name.startswith("ageix.project:Ageix_Test") for name in result["optional_scope_names"])

    realm_id = fake.realms["ageix"]["id"]
    granted_scope_ids = fake.realm_optional_scopes["ageix"]
    expected_scope_ids = {fake.scopes["ageix"][name]["id"] for name in result["optional_scope_names"]}
    assert granted_scope_ids == expected_scope_ids
    assert all(c["parentId"] == realm_id for c in fake.components["ageix"].values())


def test_ensure_public_pkce_client_creates_and_is_idempotent(monkeypatch):
    fake = FakeKeycloak()
    admin = _admin(monkeypatch, fake)
    admin.ensure_realm()

    first = admin.ensure_public_pkce_client("ageix-connector-claude-ai", redirect_uris=["https://claude.ai/callback"])
    second = admin.ensure_public_pkce_client("ageix-connector-claude-ai", redirect_uris=["https://claude.ai/callback"])

    assert first["id"] == second["id"]
    stored = fake.clients["ageix"]["ageix-connector-claude-ai"]
    assert stored["publicClient"] is True
    assert stored["serviceAccountsEnabled"] is False
    assert stored["standardFlowEnabled"] is True
    assert stored["redirectUris"] == ["https://claude.ai/callback"]
    assert stored["attributes"]["pkce.code.challenge.method"] == "S256"


def test_ensure_public_pkce_client_updates_redirect_uris(monkeypatch):
    fake = FakeKeycloak()
    admin = _admin(monkeypatch, fake)
    admin.ensure_realm()

    admin.ensure_public_pkce_client("ageix-connector-claude-ai", redirect_uris=["https://claude.ai/callback-old"])
    updated = admin.ensure_public_pkce_client("ageix-connector-claude-ai", redirect_uris=["https://claude.ai/callback-new"])

    assert updated["redirectUris"] == ["https://claude.ai/callback-new"]
    assert fake.clients["ageix"]["ageix-connector-claude-ai"]["redirectUris"] == ["https://claude.ai/callback-new"]


def test_provision_connector_client_has_no_secret_and_correct_scopes(tmp_path: Path, monkeypatch):
    fake = FakeKeycloak()
    admin = _admin(monkeypatch, fake)

    auth_config_path = tmp_path / ".ageix" / "config" / "auth.json"
    auth_config_path.parent.mkdir(parents=True)
    auth_config_path.write_text(json.dumps({
        "jwt": {
            "default_allowed_capabilities": ["*"],
            "default_allowed_projects": ["Ageix_Test"],
        },
    }), encoding="utf-8")

    service = KeycloakProvisioningService(tmp_path, admin=admin)
    result = service.provision_connector_client("claude-ai", ["https://claude.ai/callback"])

    assert result.skipped is False
    assert result.secret_path is None
    assert result.keycloak_client_id == "ageix-connector-claude-ai"
    assert any(name.startswith("ageix.capability:") for name in result.scope_names)
    assert any(name.startswith("ageix.project:Ageix_Test") for name in result.scope_names)

    client_uuid = fake.clients["ageix"]["ageix-connector-claude-ai"]["id"]
    assert fake.clients["ageix"]["ageix-connector-claude-ai"]["publicClient"] is True
    assert len(fake.default_scopes[client_uuid]) == len(result.scope_names)
