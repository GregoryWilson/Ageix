from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PatchLineageService:
    """Tracks relationships between Ageix patches and related lifecycle artifacts.

    This service is intentionally artifact-only. It does not modify repository files,
    stage patches, validate patches, promote patches, or commit changes.
    """

    VALID_RELATIONSHIP_TYPES = {
        "repair",
        "cloud_escalation",
        "supersedes",
        "followup",
        "rollback",
    }

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root).resolve()
        self.ageix_root = self.repo_root / ".ageix"
        self.lineage_root = self.ageix_root / "lineage"
        self.relationship_root = self.lineage_root / "relationships"
        self.summary_root = self.lineage_root / "summaries"

        self.relationship_root.mkdir(parents=True, exist_ok=True)
        self.summary_root.mkdir(parents=True, exist_ok=True)

    def record_patch_relationship(
        self,
        parent_patch_id: str,
        child_patch_id: str,
        relationship_type: str,
        reason: str | None = None,
        source_verification_id: str | None = None,
        repair_loop_id: str | None = None,
    ) -> dict[str, Any]:
        if relationship_type not in self.VALID_RELATIONSHIP_TYPES:
            raise ValueError(f"Unsupported relationship_type: {relationship_type}")

        if parent_patch_id == child_patch_id:
            raise ValueError("A patch cannot be related to itself.")

        relationship_id = self._new_id("relationship")
        artifact = {
            "relationship_id": relationship_id,
            "parent_patch_id": parent_patch_id,
            "child_patch_id": child_patch_id,
            "relationship_type": relationship_type,
            "reason": reason,
            "source_verification_id": source_verification_id,
            "repair_loop_id": repair_loop_id,
            "timestamp": self._now(),
        }

        self._write_json(self.relationship_root / relationship_id / "relationship.json", artifact)
        return artifact

    def record_repair_relationship(
        self,
        parent_patch_id: str,
        child_patch_id: str,
        source_verification_id: str | None = None,
        repair_loop_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return self.record_patch_relationship(
            parent_patch_id=parent_patch_id,
            child_patch_id=child_patch_id,
            relationship_type="repair",
            reason=reason,
            source_verification_id=source_verification_id,
            repair_loop_id=repair_loop_id,
        )

    def record_cloud_escalation_relationship(
        self,
        parent_patch_id: str,
        child_patch_id: str,
        source_verification_id: str | None = None,
        repair_loop_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return self.record_patch_relationship(
            parent_patch_id=parent_patch_id,
            child_patch_id=child_patch_id,
            relationship_type="cloud_escalation",
            reason=reason,
            source_verification_id=source_verification_id,
            repair_loop_id=repair_loop_id,
        )

    def record_verification_relationship(
        self,
        patch_id: str,
        verification_id: str,
        result: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        relationship_id = self._new_id("verification_link")
        artifact = {
            "relationship_id": relationship_id,
            "patch_id": patch_id,
            "verification_id": verification_id,
            "relationship_type": "verification",
            "result": result,
            "reason": reason,
            "timestamp": self._now(),
        }

        self._write_json(self.relationship_root / relationship_id / "relationship.json", artifact)
        return artifact

    def record_commit_relationship(
        self,
        patch_id: str,
        commit_record_id: str,
        git_commit: str | None = None,
        promotion_id: str | None = None,
    ) -> dict[str, Any]:
        relationship_id = self._new_id("commit_link")
        artifact = {
            "relationship_id": relationship_id,
            "patch_id": patch_id,
            "commit_record_id": commit_record_id,
            "git_commit": git_commit,
            "promotion_id": promotion_id,
            "relationship_type": "commit",
            "timestamp": self._now(),
        }

        self._write_json(self.relationship_root / relationship_id / "relationship.json", artifact)
        return artifact

    def get_relationships(self) -> list[dict[str, Any]]:
        relationships: list[dict[str, Any]] = []

        if not self.relationship_root.exists():
            return relationships

        for path in sorted(self.relationship_root.rglob("relationship.json")):
            relationships.append(json.loads(path.read_text(encoding="utf-8")))

        return relationships

    def find_root_patch(self, patch_id: str) -> str:
        current = patch_id
        visited: set[str] = set()

        while True:
            if current in visited:
                raise ValueError(f"Cycle detected while resolving lineage for {patch_id}")

            visited.add(current)
            parent = self._parent_for(current)

            if parent is None:
                return current

            current = parent

    def build_lineage_graph(self, patch_id: str) -> dict[str, Any]:
        root_patch_id = self.find_root_patch(patch_id)
        relationships = self.get_relationships()
        patch_edges = [
            rel
            for rel in relationships
            if rel.get("parent_patch_id") or rel.get("child_patch_id")
        ]

        related_patch_ids = self._collect_descendants(root_patch_id, patch_edges)
        related_patch_ids.add(root_patch_id)

        related_edges = [
            rel
            for rel in patch_edges
            if rel.get("parent_patch_id") in related_patch_ids
            or rel.get("child_patch_id") in related_patch_ids
        ]

        related_lifecycle_links = [
            rel
            for rel in relationships
            if rel.get("patch_id") in related_patch_ids
        ]

        graph = {
            "lineage_id": self._new_id("lineage"),
            "root_patch_id": root_patch_id,
            "requested_patch_id": patch_id,
            "patch_ids": sorted(related_patch_ids),
            "patch_relationships": related_edges,
            "lifecycle_relationships": related_lifecycle_links,
            "generated_at": self._now(),
        }

        self._write_json(self.summary_root / graph["lineage_id"] / "lineage.json", graph)
        return graph

    def get_lineage_metrics(self, patch_id: str) -> dict[str, int]:
        graph = self.build_lineage_graph(patch_id)
        patch_relationships = graph["patch_relationships"]
        lifecycle_relationships = graph["lifecycle_relationships"]

        return {
            "repair_attempts": sum(1 for rel in patch_relationships if rel.get("relationship_type") == "repair"),
            "cloud_escalations": sum(1 for rel in patch_relationships if rel.get("relationship_type") == "cloud_escalation"),
            "verification_failures": sum(
                1
                for rel in lifecycle_relationships
                if rel.get("relationship_type") == "verification" and str(rel.get("result", "")).upper() == "FAIL"
            ),
            "verification_passes": sum(
                1
                for rel in lifecycle_relationships
                if rel.get("relationship_type") == "verification" and str(rel.get("result", "")).upper() == "PASS"
            ),
            "commits": sum(1 for rel in lifecycle_relationships if rel.get("relationship_type") == "commit"),
        }

    def explain_patch(self, patch_id: str) -> str:
        graph = self.build_lineage_graph(patch_id)
        metrics = self.get_lineage_metrics(patch_id)
        root = graph["root_patch_id"]
        lines = [
            f"Patch lineage for {patch_id}",
            "",
            f"Origin: {root}",
            "",
            "Patch relationships:",
        ]

        if graph["patch_relationships"]:
            for rel in graph["patch_relationships"]:
                lines.append(
                    f"  {rel['parent_patch_id']} -> {rel['child_patch_id']} "
                    f"({rel['relationship_type']})"
                )
        else:
            lines.append("  No parent/child patch relationships recorded.")

        lines.extend(["", "Lifecycle links:"])

        if graph["lifecycle_relationships"]:
            for rel in graph["lifecycle_relationships"]:
                if rel.get("relationship_type") == "verification":
                    lines.append(
                        f"  {rel['patch_id']} -> verification {rel['verification_id']} "
                        f"({rel.get('result')})"
                    )
                elif rel.get("relationship_type") == "commit":
                    git_commit = rel.get("git_commit") or "unknown"
                    lines.append(
                        f"  {rel['patch_id']} -> commit record {rel['commit_record_id']} "
                        f"({git_commit})"
                    )
        else:
            lines.append("  No verification or commit links recorded.")

        lines.extend(
            [
                "",
                "Metrics:",
                f"  Repair attempts: {metrics['repair_attempts']}",
                f"  Cloud escalations: {metrics['cloud_escalations']}",
                f"  Verification failures: {metrics['verification_failures']}",
                f"  Verification passes: {metrics['verification_passes']}",
                f"  Commits: {metrics['commits']}",
            ]
        )

        return "\n".join(lines)

    def _parent_for(self, patch_id: str) -> str | None:
        parents = [
            rel.get("parent_patch_id")
            for rel in self.get_relationships()
            if rel.get("child_patch_id") == patch_id
        ]

        if len(parents) > 1:
            raise ValueError(f"Multiple parents found for patch {patch_id}: {parents}")

        return parents[0] if parents else None

    def _collect_descendants(self, root_patch_id: str, edges: list[dict[str, Any]]) -> set[str]:
        descendants: set[str] = set()
        frontier = [root_patch_id]

        while frontier:
            parent = frontier.pop()
            children = [rel["child_patch_id"] for rel in edges if rel.get("parent_patch_id") == parent]

            for child in children:
                if child not in descendants:
                    descendants.add(child)
                    frontier.append(child)

        return descendants

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
