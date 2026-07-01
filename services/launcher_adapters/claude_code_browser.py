from __future__ import annotations

from models.worker_admission_ticket import WorkerAdmissionTicket
from models.worker_launch_profile import WorkerLaunchProfile
from models.worker_launch_request import WorkerLaunchRequest
from services.launcher_adapters.base import LauncherAdapter, LauncherHandoff


class ClaudeCodeBrowserLauncherAdapter(LauncherAdapter):
    """Manual browser handoff adapter for Claude Code, per PROP-934ADA8E57B8.

    Produces human-readable, non-authoritative handoff instructions that Greg
    follows to start Claude Code in the browser and admit it into the governed
    DevJob workflow. It generates NO executing URL, launches no process, and
    performs no work. The admitted worker must still redeem the admission ticket
    and retrieve governed context from Ageix through existing capabilities.
    """

    adapter_key = "claude_code_browser"
    expected_worker_type = "claude_code"

    def build_handoff(
        self,
        *,
        ticket: WorkerAdmissionTicket,
        profile: WorkerLaunchProfile,
        request: WorkerLaunchRequest,
    ) -> LauncherHandoff:
        instructions = [
            "Manual handoff for Greg. Ageix has NOT executed any worker; this is a "
            "governed handoff only.",
            f"1. Open Claude Code in the browser for the '{ticket.project_id}' project.",
            "2. Connect Claude Code to the Ageix MCP server (governed interface).",
            f"3. Redeem admission ticket {ticket.ticket_id} via "
            f"worker.admission.ticket.redeem (worker_id={ticket.worker_id}).",
            f"4. Retrieve governed context via the required next capability: "
            f"{ticket.required_next_capability}. Do not act on launch text as authority.",
            f"5. Operate under permission mode '{ticket.permission_mode.value}'. Block on "
            "ambiguity, missing evidence, unsafe instructions, or scope conflict.",
            "6. Chair/human authority (Greg) remains the execution boundary. Do not assume "
            "approval, complete the DevJob, or bypass governance.",
        ]
        launch_reference = {
            "adapter": self.adapter_key,
            "handoff_mode": "manual",
            "worker_target": "claude_code_web",
            "authoritative": False,
            "note": (
                "Non-authoritative handoff descriptor. Greg initiates the worker "
                "manually; Ageix performs no execution and opens no process."
            ),
        }
        return LauncherHandoff(
            handoff_instructions=instructions,
            launch_reference=launch_reference,
            adapter_notes=["browser_manual_handoff_only", "no_execution_performed"],
        )
