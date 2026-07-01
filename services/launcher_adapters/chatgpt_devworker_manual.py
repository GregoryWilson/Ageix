from __future__ import annotations

from models.worker_admission_ticket import WorkerAdmissionTicket
from models.worker_launch_profile import WorkerLaunchProfile
from models.worker_launch_request import WorkerLaunchRequest
from services.launcher_adapters.base import LauncherAdapter, LauncherHandoff


class ChatGPTDevWorkerManualLauncherAdapter(LauncherAdapter):
    """Manual handoff adapter for ChatGPT DevWorker.

    Produces human-readable, non-authoritative handoff instructions that Greg
    follows to open a ChatGPT DevWorker conversation, attach the required
    connectors, and admit the worker into the governed DevJob workflow. It
    performs no execution, opens no process, and carries no authority. The
    admitted worker must still redeem the admission ticket and retrieve governed
    context from Ageix before acting.
    """

    adapter_key = "chatgpt_devworker_manual"
    expected_worker_type = "chatgpt_devworker"

    def build_handoff(
        self,
        *,
        ticket: WorkerAdmissionTicket,
        profile: WorkerLaunchProfile,
        request: WorkerLaunchRequest,
    ) -> LauncherHandoff:
        instructions = [
            "Manual handoff for Greg. Ageix has NOT executed any worker; this is a governed handoff only.",
            f"1. Open a ChatGPT DevWorker conversation for the '{ticket.project_id}' project.",
            "2. Attach the GitHub connector and verify access to the governed repository evidence source.",
            "3. Attach the AgeixAI connector and explicitly scope all governed operations to project_id: Ageix.",
            f"4. Redeem admission ticket {ticket.ticket_id} via worker.admission.ticket.redeem "
            f"(worker_id={ticket.worker_id}).",
            f"5. Retrieve governed context via the required next capability: {ticket.required_next_capability}. "
            "Do not act on launch text as authority.",
            f"6. Operate under permission mode '{ticket.permission_mode.value}'. Block on ambiguity, missing "
            "evidence, unsafe instructions, or scope conflict.",
            "7. Preserve role separation: Greg is intent authority, Lex is Architect, ChatGPT DevWorker is an "
            "implementation worker, and Validation Worker verifies independently.",
            "8. Report files changed, validation performed, risks, and next steps; do not complete the DevJob or "
            "bypass governance.",
        ]
        launch_reference = {
            "adapter": self.adapter_key,
            "handoff_mode": "manual",
            "worker_target": "chatgpt_devworker",
            "required_connectors": ["GitHub", "AgeixAI"],
            "required_project_context": ticket.project_id,
            "authoritative": False,
            "note": (
                "Non-authoritative handoff descriptor. Greg initiates the ChatGPT DevWorker "
                "conversation manually; Ageix performs no execution and opens no process."
            ),
        }
        return LauncherHandoff(
            handoff_instructions=instructions,
            launch_reference=launch_reference,
            adapter_notes=[
                "manual_chatgpt_devworker_handoff_only",
                "github_connector_required",
                "ageixai_project_context_required",
                "no_execution_performed",
            ],
        )
