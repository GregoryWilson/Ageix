from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.repo_write_governance_service import RepoWriteGovernanceService
from services.repository_git_mutation_service import RepositoryGitMutationService


def register_capabilities(repo_root: Path):
    def git() -> RepositoryGitMutationService:
        return RepositoryGitMutationService(repo_root)

    def governance() -> RepoWriteGovernanceService:
        return RepoWriteGovernanceService(repo_root)

    def ok(result: dict[str, Any], mode: str) -> dict[str, Any]:
        return {"success": True, "result": result, "metadata": {"request_mode": mode, "repository_target": str(repo_root)}, "error": None}

    def denied(mode: str, decision: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": False,
            "result": {"status": "denied", "decision": decision},
            "metadata": {"request_mode": mode, "repository_target": str(repo_root)},
            "error": decision.get("reason", "authorization_denied"),
        }

    def authorize(capability_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return governance().authorize_mutation(
            capability_id=capability_id,
            sprint_id=arguments.get("sprint_id"),
            approval_id=arguments.get("approval_id"),
        )

    # --- Unauthenticated, non-destructive sync operations ---

    def repo_fetch(arguments: dict[str, Any]) -> dict[str, Any]:
        result = git().fetch(remote=str(arguments.get("remote") or "origin"))
        return ok(result, "repo_fetch")

    def repo_tag_list(arguments: dict[str, Any]) -> dict[str, Any]:
        return ok(git().tag_list(), "repo_tag_list")

    # --- Gated mutating operations: require an active sprint grant or a one-off approval ---

    def repo_pull(arguments: dict[str, Any]) -> dict[str, Any]:
        decision = authorize("repo.pull", arguments)
        if not decision.get("allowed"):
            return denied("repo_pull", decision)
        result = git().pull(remote=str(arguments.get("remote") or "origin"), branch=arguments.get("branch"))
        result["authorization"] = decision
        return ok(result, "repo_pull")

    def repo_checkout(arguments: dict[str, Any]) -> dict[str, Any]:
        decision = authorize("repo.checkout", arguments)
        if not decision.get("allowed"):
            return denied("repo_checkout", decision)
        result = git().checkout(ref=str(arguments.get("ref") or ""), create=bool(arguments.get("create") or False))
        result["authorization"] = decision
        return ok(result, "repo_checkout")

    def repo_branch_create(arguments: dict[str, Any]) -> dict[str, Any]:
        decision = authorize("repo.branch.create", arguments)
        if not decision.get("allowed"):
            return denied("repo_branch_create", decision)
        result = git().branch_create(name=str(arguments.get("name") or ""), start_point=arguments.get("start_point"))
        result["authorization"] = decision
        return ok(result, "repo_branch_create")

    def repo_branch_delete(arguments: dict[str, Any]) -> dict[str, Any]:
        decision = authorize("repo.branch.delete", arguments)
        if not decision.get("allowed"):
            return denied("repo_branch_delete", decision)
        result = git().branch_delete(name=str(arguments.get("name") or ""))
        result["authorization"] = decision
        return ok(result, "repo_branch_delete")

    def repo_tag_create(arguments: dict[str, Any]) -> dict[str, Any]:
        decision = authorize("repo.tag.create", arguments)
        if not decision.get("allowed"):
            return denied("repo_tag_create", decision)
        result = git().tag_create(name=str(arguments.get("name") or ""), message=arguments.get("message"), ref=arguments.get("ref"))
        result["authorization"] = decision
        return ok(result, "repo_tag_create")

    def repo_tag_delete(arguments: dict[str, Any]) -> dict[str, Any]:
        decision = authorize("repo.tag.delete", arguments)
        if not decision.get("allowed"):
            return denied("repo_tag_delete", decision)
        result = git().tag_delete(name=str(arguments.get("name") or ""))
        result["authorization"] = decision
        return ok(result, "repo_tag_delete")

    def repo_commit(arguments: dict[str, Any]) -> dict[str, Any]:
        decision = authorize("repo.commit", arguments)
        if not decision.get("allowed"):
            return denied("repo_commit", decision)
        paths = arguments.get("paths")
        if paths is not None and not isinstance(paths, list):
            return {"success": False, "result": {}, "metadata": {"request_mode": "repo_commit"}, "error": "paths_must_be_list"}
        result = git().commit(message=str(arguments.get("message") or ""), paths=paths)
        result["authorization"] = decision
        return ok(result, "repo_commit")

    def repo_push(arguments: dict[str, Any]) -> dict[str, Any]:
        decision = authorize("repo.push", arguments)
        if not decision.get("allowed"):
            return denied("repo_push", decision)
        result = git().push(
            remote=str(arguments.get("remote") or "origin"),
            branch=arguments.get("branch"),
            set_upstream=bool(arguments.get("set_upstream", True)),
        )
        result["authorization"] = decision
        return ok(result, "repo_push")

    # --- Push to the default branch: always requires a fresh, single-use human approval ---

    def repo_push_main(arguments: dict[str, Any]) -> dict[str, Any]:
        decision = authorize("repo.push.main", arguments)
        if not decision.get("allowed"):
            return denied("repo_push_main", decision)
        result = git().push_main(remote=str(arguments.get("remote") or "origin"))
        result["authorization"] = decision
        return ok(result, "repo_push_main")

    # --- Human-only governance management ---

    def repo_write_grant_create(arguments: dict[str, Any]) -> dict[str, Any]:
        result = governance().create_grant(
            sprint_id=str(arguments.get("sprint_id") or ""),
            granted_by=str(arguments.get("granted_by") or ""),
            capability_ids=arguments.get("capability_ids"),
            expires_at=arguments.get("expires_at"),
            reason=str(arguments.get("reason") or ""),
        )
        return ok(result, "repo_write_grant_create")

    def repo_write_grant_revoke(arguments: dict[str, Any]) -> dict[str, Any]:
        result = governance().revoke_grant(
            grant_id=str(arguments.get("grant_id") or ""),
            revoked_by=str(arguments.get("revoked_by") or ""),
        )
        return ok(result, "repo_write_grant_revoke")

    def repo_write_grant_list(arguments: dict[str, Any]) -> dict[str, Any]:
        result = governance().list_grants(
            sprint_id=arguments.get("sprint_id"),
            status=arguments.get("status"),
            limit=int(arguments.get("limit") or 20),
            offset=int(arguments.get("offset") or 0),
        )
        return ok(result, "repo_write_grant_list")

    def repo_write_approve(arguments: dict[str, Any]) -> dict[str, Any]:
        result = governance().create_approval(
            capability_id=str(arguments.get("capability_id") or ""),
            approved_by=str(arguments.get("approved_by") or ""),
            proposal_id=arguments.get("proposal_id"),
            sprint_id=arguments.get("sprint_id"),
            target_ref=arguments.get("target_ref"),
            reason=str(arguments.get("reason") or ""),
        )
        return ok(result, "repo_write_approve")

    def repo_write_approval_list(arguments: dict[str, Any]) -> dict[str, Any]:
        result = governance().list_approvals(
            capability_id=arguments.get("capability_id"),
            status=arguments.get("status"),
            limit=int(arguments.get("limit") or 20),
            offset=int(arguments.get("offset") or 0),
        )
        return ok(result, "repo_write_approval_list")

    return [
        (CapabilityDefinition(capability_id="repo.fetch", category="repository", access_level="governed_write", handler="repository.fetch", description="Fetch remote-tracking refs without modifying the working tree. Not gated -- non-destructive and reversible."), repo_fetch),
        (CapabilityDefinition(capability_id="repo.tag.list", category="repository", access_level="governed_read", handler="repository.tag.list", description="List local repository tags."), repo_tag_list),

        (CapabilityDefinition(capability_id="repo.pull", category="repository", access_level="governed_write", handler="repository.pull", description="Fast-forward-only pull from a remote. Requires an active sprint grant or a one-off human approval.", requires_proposal=True), repo_pull),
        (CapabilityDefinition(capability_id="repo.checkout", category="repository", access_level="governed_write", handler="repository.checkout", description="Checkout an existing or new branch/ref. Requires an active sprint grant or a one-off human approval.", requires_proposal=True), repo_checkout),
        (CapabilityDefinition(capability_id="repo.branch.create", category="repository", access_level="governed_write", handler="repository.branch.create", description="Create a local branch. Requires an active sprint grant or a one-off human approval.", requires_proposal=True), repo_branch_create),
        (CapabilityDefinition(capability_id="repo.branch.delete", category="repository", access_level="governed_write", handler="repository.branch.delete", description="Delete a fully-merged local branch. Requires an active sprint grant or a one-off human approval.", requires_proposal=True), repo_branch_delete),
        (CapabilityDefinition(capability_id="repo.tag.create", category="repository", access_level="governed_write", handler="repository.tag.create", description="Create a local tag. Requires an active sprint grant or a one-off human approval.", requires_proposal=True), repo_tag_create),
        (CapabilityDefinition(capability_id="repo.tag.delete", category="repository", access_level="governed_write", handler="repository.tag.delete", description="Delete a local tag. Requires an active sprint grant or a one-off human approval.", requires_proposal=True), repo_tag_delete),
        (CapabilityDefinition(capability_id="repo.commit", category="repository", access_level="governed_write", handler="repository.commit", description="Stage listed paths (optional) and create a commit. Requires an active sprint grant or a one-off human approval.", requires_proposal=True), repo_commit),
        (CapabilityDefinition(capability_id="repo.push", category="repository", access_level="governed_write", handler="repository.push", description="Push a non-default branch to a remote. Requires an active sprint grant or a one-off human approval. Refuses the default branch -- use repo.push.main.", requires_proposal=True), repo_push),

        (CapabilityDefinition(capability_id="repo.push.main", category="repository", access_level="governed_write", handler="repository.push.main", description="Push the default branch to a remote. Always requires a fresh, single-use human approval; never satisfiable by a sprint grant.", requires_proposal=True), repo_push_main),

        (CapabilityDefinition(capability_id="repo.write.grant.create", category="repository", access_level="governed_write", handler="repository.write.grant.create", description="Human-only: grant a standing sprint-level override for mutating git capabilities (excludes repo.push.main)."), repo_write_grant_create),
        (CapabilityDefinition(capability_id="repo.write.grant.revoke", category="repository", access_level="governed_write", handler="repository.write.grant.revoke", description="Human-only: revoke a sprint-level repo write grant."), repo_write_grant_revoke),
        (CapabilityDefinition(capability_id="repo.write.grant.list", category="repository", access_level="governed_read", handler="repository.write.grant.list", description="List sprint-level repo write grants."), repo_write_grant_list),
        (CapabilityDefinition(capability_id="repo.write.approve", category="repository", access_level="governed_write", handler="repository.write.approve", description="Human-only: issue a single-use approval authorizing one specific mutating git capability call."), repo_write_approve),
        (CapabilityDefinition(capability_id="repo.write.approval.list", category="repository", access_level="governed_read", handler="repository.write.approval.list", description="List one-off repo write approvals."), repo_write_approval_list),
    ]
