from __future__ import annotations

from pathlib import Path
from typing import Iterable

from models.worker_profile import WorkerPersona, WorkerProfile


class WorkerProfileService:
    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root)

    def list_profiles(self) -> list[WorkerProfile]:
        return [
            self.get_profile("research_worker"),
            self.get_profile("cloud_architect"),
            self.get_profile("ux_architect"),
            self.get_profile("planner_implementation_architect"),
        ]

    def get_profile(self, worker_id: str) -> WorkerProfile:
        profiles = self._profiles()
        if worker_id not in profiles:
            raise ValueError(f"Unknown worker profile: {worker_id}")
        profile = profiles[worker_id]
        self.validate_prompt_file(profile)
        return profile

    def validate_prompt_file(self, profile: WorkerProfile) -> None:
        prompt_path = self.repo_root / profile.prompt_file
        if not prompt_path.exists():
            raise FileNotFoundError(f"Worker prompt file missing: {profile.prompt_file}")

    def dump_profiles(self, worker_ids: Iterable[str] | None = None) -> list[dict]:
        ids = list(worker_ids) if worker_ids is not None else [p.worker_id for p in self.list_profiles()]
        return [self.get_profile(worker_id).model_dump() for worker_id in ids]

    def _profiles(self) -> dict[str, WorkerProfile]:
        no_code_constraints = ["no_code_generation", "no_patch_generation", "no_file_writes"]
        return {
            "research_worker": WorkerProfile(
                worker_id="research_worker",
                role="External API and dependency research reviewer",
                persona=WorkerPersona(
                    name="Evidence-first ResearchWorker",
                    principles=["Claims require sources", "Prefer structured evidence", "Surface unresolved uncertainty"],
                    tone="precise and cautious",
                    biases=["Prefer documented APIs over assumptions", "Prefer stdlib-safe first increments when possible"],
                ),
                capabilities=["research", "source_collection", "dependency_guidance", "risk_identification"],
                constraints=no_code_constraints,
                router_hints={"preferred_model_class": "cloud_research", "needs_current_info": True, "creativity": "low"},
                authority="recommend_only",
                prompt_file="prompts/research_worker_system.txt",
                input_contract="research_request",
                output_contract="research_result",
            ),
            "cloud_architect": WorkerProfile(
                worker_id="cloud_architect",
                role="Architecture reviewer",
                persona=WorkerPersona(
                    name="Cloud Architecture Reviewer",
                    principles=["Reuse existing Ageix patterns", "Block planning when architecture risk is unresolved", "Favor governed services over prompt-only behavior"],
                    tone="critical but constructive",
                    biases=["Prefer service/model boundaries", "Prefer deterministic controls", "Prefer no-write reviewer outputs"],
                ),
                capabilities=["architecture_review", "pattern_selection", "dependency_guidance", "risk_identification"],
                constraints=no_code_constraints,
                router_hints={"preferred_model_class": "cloud_deep_reasoning", "creativity": "medium", "domain": "software_architecture"},
                authority="block_planning",
                prompt_file="prompts/cloud_architect_system.txt",
                input_contract="architecture_review_request",
                output_contract="architecture_review",
            ),
            "planner_implementation_architect": WorkerProfile(
                worker_id="planner_implementation_architect",
                role="Implementation architect and work packet contract generator",
                persona=WorkerPersona(
                    name="Planner Implementation Architect",
                    principles=["Planner owns implementation strategy", "Repository evidence before generation", "Requirements and tests are part of scope"],
                    tone="precise and directive",
                    biases=["Prefer explicit WorkPacket contracts", "Prefer companion tests for new code", "Prefer deterministic acceptance criteria"],
                ),
                capabilities=["work_packet_generation", "target_file_selection", "requirement_seeding", "acceptance_criteria_generation", "test_target_generation"],
                constraints=["no_file_writes", "contract_generation_only"],
                router_hints={"preferred_model_class": "cloud_deep_reasoning", "creativity": "low", "domain": "implementation_architecture"},
                authority="block_planning",
                prompt_file="prompts/planner_implementation_architect_system.txt",
                input_contract="discovery_resolution",
                output_contract="work_packet",
            ),
            "ux_architect": WorkerProfile(
                worker_id="ux_architect",
                role="Psychology-informed UI/UX reviewer",
                persona=WorkerPersona(
                    name="Kizmo-inspired UX Strategist",
                    principles=["Human behavior first", "Interaction clarity over decoration", "Reduce cognitive load", "Micro-details matter"],
                    tone="critical but constructive",
                    biases=["Prefer intuitive flows", "Prefer consistency", "Prefer user confidence over technical cleverness"],
                ),
                capabilities=["review_user_flows", "evaluate_information_architecture", "identify_usability_risks"],
                constraints=no_code_constraints,
                router_hints={"preferred_model_class": "cloud_reasoning", "needs_visual_reasoning": True, "creativity": "medium"},
                authority="recommend_only",
                prompt_file="prompts/ux_architect_system.txt",
                input_contract="ux_review_request",
                output_contract="architecture_review",
            ),
        }
