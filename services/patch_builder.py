from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from contracts.patch_contract import PatchFile, PatchProposal

class PatchBuilder:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.staged_root = self.repo_root / ".ageix" / "staged"

    def stage_patch(
        self,
        proposal: PatchProposal,
        *,
        proposal_quality: dict | None = None,
        requirement_trace: dict | None = None,
        behavior_verification: dict | None = None,
        validation_summary: dict | None = None,
        validation_evidence: dict | None = None,
        runtime_validation_summary: dict | None = None,
        runtime_execution_evidence: dict | None = None,
        confidence_summary: dict | None = None,
        promotion_readiness_summary: dict | None = None,
        governance_review_packet: dict | None = None,
    ) -> dict:
        patch_id = f"patch_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        patch_dir = self.staged_root / patch_id
        files_dir = patch_dir / "files"
        originals_dir = patch_dir / "originals"

        files_dir.mkdir(parents=True, exist_ok=False)
        originals_dir.mkdir(parents=True, exist_ok=True)

        changed_files: list[str] = []

        for patch_file in proposal.files:
            rel_path = self._safe_relative_path(patch_file.path)
            live_path = self.repo_root / rel_path
            staged_path = files_dir / rel_path
            original_path = originals_dir / rel_path

            staged_path.parent.mkdir(parents=True, exist_ok=True)
            original_path.parent.mkdir(parents=True, exist_ok=True)

            if patch_file.operation in {"modify", "delete"}:
                if not live_path.exists():
                    raise FileNotFoundError(f"Cannot {patch_file.operation} missing file: {rel_path}")

                shutil.copy2(live_path, original_path)

            if patch_file.operation in {"create", "modify"}:
                if patch_file.content is None:
                    raise ValueError(f"Patch file content required for {patch_file.operation}: {rel_path}")

                staged_path.write_text(patch_file.content, encoding="utf-8")

            elif patch_file.operation == "delete":
                staged_path.write_text("", encoding="utf-8")

            changed_files.append(str(rel_path))

        diff_text = self._build_diff(originals_dir, files_dir)
        (patch_dir / "diff.patch").write_text(diff_text, encoding="utf-8")

        manifest = {
            "patch_id": patch_id,
            "status": "staged",
            "objective": proposal.objective,
            "summary": proposal.summary,
            "reasoning": proposal.reasoning,
            "changed_files": changed_files,
            "patch_dir": str(patch_dir),
            "diff_file": str(patch_dir / "diff.patch"),
            "proposal_quality": proposal_quality,
            "requirement_trace": requirement_trace,
            "behavior_verification": behavior_verification,
            "validation_summary": validation_summary,
            "validation_evidence": validation_evidence,
            "runtime_validation_summary": runtime_validation_summary,
            "runtime_execution_evidence": runtime_execution_evidence,
            "confidence_summary": confidence_summary,
            "promotion_readiness_summary": promotion_readiness_summary,
            "governance_review_packet": governance_review_packet,
        }

        (patch_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

        return manifest

    def _safe_relative_path(self, raw_path: str) -> Path:
        rel_path = Path(raw_path)

        if rel_path.is_absolute():
            raise ValueError(f"Absolute paths are not allowed: {raw_path}")

        resolved = (self.repo_root / rel_path).resolve()

        if not str(resolved).startswith(str(self.repo_root)):
            raise ValueError(f"Path escapes repository root: {raw_path}")

        if ".ageix" in rel_path.parts:
            raise ValueError(f"Patches may not target .ageix internals: {raw_path}")

        return rel_path

    def _build_diff(self, originals_dir: Path, files_dir: Path) -> str:
        result = subprocess.run(
            ["git", "diff", "--no-index", "--", str(originals_dir), str(files_dir)],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )

        # git diff --no-index returns 1 when differences exist.
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr.strip())

        return result.stdout
    

    def stage_patch_from_deliverable(
        self,
        deliverable: dict,
        *,
        proposal_quality: dict | None = None,
        requirement_trace: dict | None = None,
        behavior_verification: dict | None = None,
        validation_summary: dict | None = None,
        validation_evidence: dict | None = None,
        runtime_validation_summary: dict | None = None,
        runtime_execution_evidence: dict | None = None,
        confidence_summary: dict | None = None,
        promotion_readiness_summary: dict | None = None,
        governance_review_packet: dict | None = None,
    ) -> dict:
        files: list[PatchFile] = []

        for change in deliverable.get("changes", []):
            raw_operation = change.get("operation")

            if raw_operation == "replace_file":
                operation = "modify"
            elif raw_operation == "create_file":
                operation = "create"
            elif raw_operation in {"create", "modify", "delete"}:
                operation = raw_operation
            
            else:
                raise ValueError(f"Unsupported patch operation: {raw_operation}")

            content=change.get("content")
            if isinstance(content, str) and not content.endswith("\n"):
                content += "\n"

            files.append(
                PatchFile(
                    path=change["path"],
                    operation=operation,
                    content=content,                    
                )
            )

        proposal = PatchProposal(
            objective=deliverable.get("objective", ""),
            summary=deliverable.get("summary", ""),
            reasoning=deliverable.get("reasoning", ""),
            files=files,
        )

        return self.stage_patch(
            proposal,
            proposal_quality=proposal_quality,
            requirement_trace=requirement_trace,
            behavior_verification=behavior_verification,
            validation_summary=validation_summary,
            validation_evidence=validation_evidence,
            runtime_validation_summary=runtime_validation_summary,
            runtime_execution_evidence=runtime_execution_evidence,
            confidence_summary=confidence_summary,
            promotion_readiness_summary=promotion_readiness_summary,
            governance_review_packet=governance_review_packet,
        )