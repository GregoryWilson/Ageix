from __future__ import annotations

from pathlib import Path

from services.ageix_architecture_baseline_service import AgeixArchitectureBaselineService
from services.architecture_registry_service import ArchitectureRegistryService
from services.project_registry_service import ProjectRegistryService

EXPECTED_SERVICE_IDS = {
    "ConversationService": "ARCH-AGEIX-SVC-CONVERSATIONSERVICE",
    "TurnService": "ARCH-AGEIX-SVC-TURNSERVICE",
    "ParticipantService": "ARCH-AGEIX-SVC-PARTICIPANTSERVICE",
    "HandoffService": "ARCH-AGEIX-SVC-HANDOFFSERVICE",
}


def test_shared_conversation_component_registered_under_session_platform(tmp_path: Path) -> None:
    ProjectRegistryService(tmp_path).ensure_official_ageix_project()
    AgeixArchitectureBaselineService(tmp_path).populate()
    registry = ArchitectureRegistryService(tmp_path)

    component = registry.require_node("Ageix.SessionPlatform.SharedConversation")

    assert component.architecture_id == "ARCH-AGEIX-SESSIONPLATFORM-SHAREDCONVERSATION"
    assert component.parent_id == "ARCH-AGEIX-SESSIONPLATFORM"
    assert component.node_type.value == "component"
    assert component.status.value == "active"
    assert component.description_state.value == "approved"


def test_shared_conversation_services_registered_with_target_ids(tmp_path: Path) -> None:
    ProjectRegistryService(tmp_path).ensure_official_ageix_project()
    AgeixArchitectureBaselineService(tmp_path).populate()
    registry = ArchitectureRegistryService(tmp_path)

    for service_name, architecture_id in EXPECTED_SERVICE_IDS.items():
        service = registry.require_node(f"Ageix.SessionPlatform.SharedConversation.{service_name}")

        assert service.architecture_id == architecture_id
        assert service.parent_id == "ARCH-AGEIX-SESSIONPLATFORM-SHAREDCONVERSATION"
        assert service.node_type.value == "service"
        assert service.status.value == "active"
        assert service.description_state.value == "approved"
        assert registry.get_node(architecture_id) is not None


def test_baseline_populate_is_idempotent_for_shared_conversation_nodes(tmp_path: Path) -> None:
    ProjectRegistryService(tmp_path).ensure_official_ageix_project()
    service = AgeixArchitectureBaselineService(tmp_path)
    service.populate()
    first_count = service.populate()["created_node_count"]

    assert first_count == 0
