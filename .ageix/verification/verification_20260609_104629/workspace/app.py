import json
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional, Any
from router import route_prompt, config
from health import get_health
import traceback
import time
import uuid
from planner import plan_task
from chair import build_chair_message, build_agent_turn_summary
from agents.planner_agent import execute_planner_agent
from collaboration_turn import CollaborationTurn
from collaboration_router import route_collaboration_turn
from work_order import WorkOrder
from work_order_runner import run_work_order
from chair import build_agent_registry
from store import (
    init_db,
    create_conversation,
    add_message,
    get_messages,
    get_project_state,
    set_project_state,
    create_task,
    get_task,
    list_tasks,
    update_task,
    get_task_events,
    get_task_tree,
    get_task_status_summary,
    get_next_action_task,
    add_agent_turn,
    get_agent_turns,
    get_sibling_tasks,
)

app = FastAPI(title="Ageix Gateway")
init_db()

class ChatRequest(BaseModel):
    prompt: str

def get_known_project_files() -> list[str]:
    return [
        "app.py",
        "router.py",
        "config.yaml",
        "store.py",
        "planner.py",
        "planner_agent.py",
        "chair.py",
        "health.py",
        "logger.py",
        "llm/router.py",
        "llm/schemas.py",
        "providers/ollama.py",
        "providers/openrouter.py",
        "safety/scrubber.py",
    ]

def build_conversation_prompt(summary: str, history: List[dict], new_message: str) -> str:
    prompt_parts = [
        "System: You are Ageix, a local-first AI gateway. Continue the conversation using the prior context."
    ]

    if summary:
        prompt_parts.append(f"Conversation Summary:\n{summary}")

    prompt_parts.append("Recent Messages:")

    for msg in history[-20:]:
        role = msg.get("role", "user").capitalize()
        content = msg.get("content", "")
        prompt_parts.append(f"{role}: {content}")

    prompt_parts.append(f"User: {new_message}")
    prompt_parts.append("Assistant:")

    return "\n\n".join(prompt_parts)

class Message(BaseModel):
    role: str
    content: str

class ConversationMessageRequest(BaseModel):
    content: str
    role: Optional[str] = "user"

class OpenAIChatRequest(BaseModel):
    model: Optional[str] = "ageix"
    messages: List[Message]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False

class CreateTaskRequest(BaseModel):
    conversation_id: str
    title: str
    description: Optional[str] = ""
    priority: Optional[str] = "normal"
    owner: Optional[str] = "user"


class UpdateTaskRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    owner: Optional[str] = None

class AgentTurnRequest(BaseModel):
    task_id: str
    conversation_id: str
    agent_name: str
    content: str
    visibility: Optional[str] = "internal"
    turn_type: Optional[str] = "comment"
    metadata: Optional[dict] = {}

@app.get("/")
def root():
    return {"status": "Ageix Gateway online"}


@app.get("/health")
def health():
    return get_health(config)


@app.post("/chat")
def chat(req: ChatRequest):
    try:
        return route_prompt(req.prompt)
    except Exception as e:
        return {
            "error": str(e),
            "trace": traceback.format_exc()
        }

@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "ageix",
                "object": "model",
                "owned_by": "ageix"
            }
        ]
    }

@app.post("/v1/chat/completions")
def openai_chat(req: OpenAIChatRequest):
    try:
        if req.stream:
            return {
                "error": {
                    "message": "Streaming is not supported yet.",
                    "type": "unsupported_feature"
                }
            }

        prompt = messages_to_prompt(req.messages)

        result = route_prompt(prompt)

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": result.get("model", req.model),
            "ageix": {
                "route": result.get("route"),
                "reason": result.get("reason"),
                "model_key": result.get("model_key"),
                "elapsed_ms": result.get("elapsed_ms")
            },
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": result.get("response", "")
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None
            }
        }

    except Exception as e:
        return {
            "error": {
                "message": str(e),
                "type": "server_error",
                "trace": traceback.format_exc()
            }
        }

@app.post("/v1/ageix/conversations/{conversation_id}/messages")
def conversation_message(conversation_id: str, req: ConversationMessageRequest):
    try:
        create_conversation(conversation_id)

        user_message_id = uuid.uuid4().hex
        add_message(
            message_id=user_message_id,
            conversation_id=conversation_id,
            role=req.role or "user",
            content=req.content,
            metadata={}
        )

        state = get_project_state(conversation_id)
        summary = state.get("conversation_summary", "")

        history = get_messages(conversation_id, limit=20)
        prompt = build_conversation_prompt(summary, history, req.content)

        result = route_prompt(prompt)

        assistant_message_id = uuid.uuid4().hex
        add_message(
            message_id=assistant_message_id,
            conversation_id=conversation_id,
            role="assistant",
            content=result.get("response", ""),
            metadata={
                "route": result.get("route"),
                "reason": result.get("reason"),
                "model_key": result.get("model_key"),
                "model": result.get("model"),
                "elapsed_ms": result.get("elapsed_ms"),
                "context_message_count": len(history),
            }
        )

        return {
            "conversation_id": conversation_id,
            "message_id": assistant_message_id,
            "ageix": {
                "route": result.get("route"),
                "reason": result.get("reason"),
                "model_key": result.get("model_key"),
                "model": result.get("model"),
                "elapsed_ms": result.get("elapsed_ms"),
            },
            "response": result.get("response", "")
        }

    except Exception as e:
        return {
            "error": {
                "message": str(e),
                "type": "server_error",
                "trace": traceback.format_exc()
            }
        }


@app.get("/v1/ageix/conversations/{conversation_id}/messages")
def conversation_history(conversation_id: str, limit: int = 50):
    return {
        "conversation_id": conversation_id,
        "messages": get_messages(conversation_id, limit)
    }

class ConversationSummaryRequest(BaseModel):
    summary: str


@app.post("/v1/ageix/conversations/{conversation_id}/summary")
def update_conversation_summary(conversation_id: str, req: ConversationSummaryRequest):
    try:
        create_conversation(conversation_id)

        state = get_project_state(conversation_id)
        state["conversation_summary"] = req.summary

        set_project_state(conversation_id, state)

        return {
            "conversation_id": conversation_id,
            "conversation_summary": req.summary
        }

    except Exception as e:
        return {
            "error": {
                "message": str(e),
                "type": "server_error",
                "trace": traceback.format_exc()
            }
        }


@app.get("/v1/ageix/conversations/{conversation_id}/summary")
def get_conversation_summary(conversation_id: str):
    state = get_project_state(conversation_id)

    return {
        "conversation_id": conversation_id,
        "conversation_summary": state.get("conversation_summary", "")
    }

@app.post("/v1/ageix/tasks")
def create_task_endpoint(req: CreateTaskRequest):
    try:
        create_conversation(req.conversation_id)

        task_id = uuid.uuid4().hex
        task = create_task(
            task_id=task_id,
            conversation_id=req.conversation_id,
            title=req.title,
            description=req.description or "",
            priority=req.priority or "normal",
            owner=req.owner or "user",
        )

        return {"task": task}

    except Exception as e:
        return {
            "error": {
                "message": str(e),
                "type": "server_error",
                "trace": traceback.format_exc()
            }
        }


@app.get("/v1/ageix/tasks")
def list_tasks_endpoint(conversation_id: Optional[str] = None):
    return {
        "tasks": list_tasks(conversation_id)
    }


@app.get("/v1/ageix/tasks/{task_id}")
def get_task_endpoint(task_id: str):
    task = get_task(task_id)

    if not task:
        return {
            "error": {
                "message": f"Task not found: {task_id}",
                "type": "not_found"
            }
        }

    return {
        "task": task,
        "events": get_task_events(task_id)
    }


@app.patch("/v1/ageix/tasks/{task_id}")
def update_task_endpoint(task_id: str, req: UpdateTaskRequest):
    try:
        task = update_task(
            task_id,
            req.model_dump(exclude_none=True)
        )

        if not task:
            return {
                "error": {
                    "message": f"Task not found: {task_id}",
                    "type": "not_found"
                }
            }

        return {
            "task": task,
            "events": get_task_events(task_id)
        }

    except Exception as e:
        return {
            "error": {
                "message": str(e),
                "type": "server_error",
                "trace": traceback.format_exc()
            }
        }

@app.post("/v1/ageix/tasks/{task_id}/plan")
def plan_task_endpoint(task_id: str):
    try:
        parent = get_task(task_id)

        if not parent:
            return {
                "error": {
                    "message": f"Task not found: {task_id}",
                    "type": "not_found"
                }
            }

        plan = plan_task(parent)
        created_subtasks = []

        for subtask in plan["subtasks"]:
            child_id = uuid.uuid4().hex

            child = create_task(
                task_id=child_id,
                conversation_id=parent["conversation_id"],
                title=subtask["title"],
                description=subtask.get("description", ""),
                priority=subtask.get("priority", parent.get("priority", "normal")),
                owner=subtask.get("owner", "planner"),
                parent_task_id=parent["id"],
            )

            created_subtasks.append(child)

        update_task(parent["id"], {
            "status": "planned",
            "owner": "chair"
        })

        return {
            "parent_task": get_task(parent["id"]),
            "plan": plan,
            "created_subtasks": created_subtasks,
        }

    except Exception as e:
        return {
            "error": {
                "message": str(e),
                "type": "server_error",
                "trace": traceback.format_exc()
            }
        }

@app.get("/v1/ageix/tasks/{task_id}/tree")
def get_task_tree_endpoint(task_id: str):
    tree = get_task_tree(task_id)

    if not tree:
        return {
            "error": {
                "message": f"Task not found: {task_id}",
                "type": "not_found"
            }
        }

    return tree

@app.get("/v1/ageix/tasks/{task_id}/status")
def get_task_status_endpoint(
    task_id: str,
    include_tree: bool = False
):
    status = get_task_status_summary(task_id)

    if not status:
        return {
            "error": {
                "message": f"Task not found: {task_id}",
                "type": "not_found"
            }
        }

    if include_tree:
        status["tree"] = get_task_tree(task_id)

    return status

def messages_to_prompt(messages: List[Message]) -> str:
    prompt_parts = [
        "System: Respond in English unless the user explicitly asks for another language."
    ]

    for msg in messages:
        role = msg.role.lower()

        if role == "system":
            prompt_parts.append(f"System: {msg.content}")
        elif role == "user":
            prompt_parts.append(f"User: {msg.content}")
        elif role == "assistant":
            prompt_parts.append(f"Assistant: {msg.content}")
        else:
            prompt_parts.append(f"{msg.role}: {msg.content}")

    prompt_parts.append("Assistant:")

    return "\n\n".join(prompt_parts)


@app.get("/v1/ageix/tasks/{task_id}/chair")
def get_task_chair_endpoint(task_id: str):
    status = get_task_status_summary(task_id)

    if not status:
        return {
            "error": {
                "message": f"Task not found: {task_id}",
                "type": "not_found"
            }
        }

    return {
        "speaker": "chair",
        "role": "pmo",
        "task_id": task_id,
        "message": build_chair_message(status),
        "status": status["status"],
        "progress": status["progress"],
        "next_actions": status["next_actions"],
    }

@app.post("/v1/ageix/tasks/{task_id}/chair/advance")
def chair_advance_task_endpoint(task_id: str):
    try:
        parent = get_task(task_id)

        if not parent:
            return {
                "error": {
                    "message": f"Task not found: {task_id}",
                    "type": "not_found"
                }
            }

        next_task = get_next_action_task(task_id)

        if not next_task:
            return {
                "speaker": "chair",
                "role": "pmo",
                "task_id": task_id,
                "message": "No child task is available to advance.",
                "next_task": None,
            }

        update_task(parent["id"], {
            "status": "in_progress",
            "owner": "chair",
        })

        updated_child = update_task(next_task["id"], {
            "status": "in_progress",
            "owner": next_task.get("owner") or "planner",
        })

        if updated_child is None:
            raise RuntimeError(
                f"Failed to update task {next_task['id']}"
            )

        add_agent_turn(
            turn_id=uuid.uuid4().hex,
            task_id=updated_child["id"],
            conversation_id=updated_child["conversation_id"],
            agent_name="chair",
            visibility="internal",
            turn_type="assignment",
            content=f"Chair advanced task '{updated_child['title']}' to in_progress.",
            metadata={
                "parent_task_id": parent["id"]
            }
        )

        status = get_task_status_summary(parent["id"])

        if status is None:
            raise RuntimeError(
                f"Unable to generate status summary for task {parent['id']}"
            )

        return {
            "speaker": "chair",
            "role": "pmo",
            "message": build_chair_message(status),
            "advanced_task": updated_child,
            "status": status,
        }

    except Exception as e:
        return {
            "error": {
                "message": str(e),
                "type": "server_error",
                "trace": traceback.format_exc()
            }
        }


@app.post("/v1/ageix/agent-turns")
def create_agent_turn_endpoint(req: AgentTurnRequest):
    try:
        add_agent_turn(
            turn_id=uuid.uuid4().hex,
            task_id=req.task_id,
            conversation_id=req.conversation_id,
            agent_name=req.agent_name,
            visibility=req.visibility or "internal",
            turn_type=req.turn_type or "comment",
            content=req.content,
            metadata=req.metadata or {},
        )

        return {
            "status": "recorded"
        }

    except Exception as e:
        return {
            "error": {
                "message": str(e),
                "type": "server_error",
                "trace": traceback.format_exc()
            }
        }


@app.get("/v1/ageix/tasks/{task_id}/agent-turns")
def get_agent_turns_endpoint(task_id: str):
    return {
        "task_id": task_id,
        "agent_turns": get_agent_turns(task_id),
    }


@app.get("/v1/ageix/tasks/{task_id}/chair/briefing")
def chair_briefing_endpoint(task_id: str):
    status = get_task_status_summary(task_id)

    if not status:
        return {
            "error": {
                "message": f"Task not found: {task_id}",
                "type": "not_found"
            }
        }

    turns = get_agent_turns(task_id)

    return {
        "speaker": "chair",
        "role": "pmo",
        "task_id": task_id,
        "status_message": build_chair_message(status),
        "agent_activity": build_agent_turn_summary(turns),
        "next_actions": status["next_actions"],
        "progress": status["progress"],
    }

@app.post("/v1/ageix/tasks/{task_id}/run")
def run_task_agent_endpoint(task_id: str):
    try:
        task = get_task(task_id)

        if not task:
            return {
                "error": {
                    "message": f"Task not found: {task_id}",
                    "type": "not_found"
                }
            }

        owner = task.get("owner") or "planner"

        if owner != "planner":
            return {
                "error": {
                    "message": f"No runnable agent is configured for owner '{owner}'.",
                    "type": "unsupported_agent"
                }
            }

        parent_task = None
        if task.get("parent_task_id"):
            parent_task = get_task(task["parent_task_id"])

        state = get_project_state(task["conversation_id"])
        conversation_summary = state.get("conversation_summary", "")

        recent_messages = get_messages(task["conversation_id"], limit=10)
        sibling_tasks = get_sibling_tasks(task)
        task_events = get_task_events(task_id)

        planner_result = execute_planner_agent(
            task=task,
            parent_task=parent_task,
            sibling_tasks=sibling_tasks,
            conversation_summary=conversation_summary,
            recent_messages=recent_messages,
            task_events=task_events,
            known_files=get_known_project_files(),
        )

        add_agent_turn(
            turn_id=uuid.uuid4().hex,
            task_id=task_id,
            conversation_id=task["conversation_id"],
            agent_name="planner",
            visibility="internal",
            turn_type="analysis",
            content=json.dumps(planner_result["content"]),
            metadata={
                "route": planner_result.get("route"),
                "model_key": planner_result.get("model_key"),
                "model": planner_result.get("model"),
                "reason": planner_result.get("reason"),
                "elapsed_ms": planner_result.get("elapsed_ms"),
                "raw_response": planner_result.get("raw_response"),
            }
        )

        updated_task = update_task(task_id, {
            "status": "completed"
        })

        if updated_task is None:
            raise RuntimeError(f"Failed to update task {task_id}")

        return {
            "task": updated_task,
            "agent_result": planner_result,
            "chair_briefing": build_agent_turn_summary(get_agent_turns(task_id)),
        }

    except Exception as e:
        return {
            "error": {
                "message": str(e),
                "type": "server_error",
                "trace": traceback.format_exc()
            }
        }
    

@app.post("/v1/ageix/collaboration/turns")
def post_collaboration_turn(turn: CollaborationTurn):
    try:
        create_conversation(turn.conversation_id)

        add_message(
            message_id=uuid.uuid4().hex,
            conversation_id=turn.conversation_id,
            role=turn.speaker,
            content=turn.content,
            metadata={
                "target": turn.target,
                "intent": turn.intent,
                **turn.metadata,
            },
        )

        decision = route_collaboration_turn(turn)

        deliverable = {}
        success_criteria = []
        
        if not decision.should_execute:
            return {
                "conversation_id": turn.conversation_id,
                "turn": turn.model_dump(),
                "decision": decision.model_dump(),
                "status": "recorded",
            }
        
        if decision.target_agent == "repository":
            deliverable = {
                "type": "repository_analysis",
                "required_sections": [
                    "summary",
                    "files",
                    "file_count",
                    "read_files",
                    "searches",
                    "risks",
                    "questions",
                ],
            }
            success_criteria = [
                "Summarizes repository inspection",
                "Lists repository files",
                "Reports file count",
                "Includes requested file reads",
                "Includes requested code searches",
                "Identifies risks",
                "Asks questions if blocked",
            ]
        else:
            deliverable = {
                "type": "change_plan",
                "required_sections": [
                    "summary",
                    "files_to_read",
                    "files_to_modify",
                    "files_to_create",
                    "planned_actions",
                    "risks",
                    "questions",
                ],
            }
            success_criteria = [
                "Summarizes intended work",
                "Lists files that need to be read",
                "Lists files that may need modification",
                "Lists files that may need creation",
                "Lists planned actions",
                "Identifies risks",
                "Asks questions if blocked",
            ]

        work_order = WorkOrder(
            work_order_id=uuid.uuid4().hex,
            agent=decision.target_agent or "dev_worker",
            objective=decision.objective,
            instructions=decision.instructions,
            input_artifacts=[],
            deliverable=deliverable,
            success_criteria=success_criteria,
            constraints={
                "source": "collaboration_turn",
                "speaker": turn.speaker,
                "execution_mode": "proposal_only",
                "no_file_writes": True,
            },
        )

        result = run_work_order(
            work_order=work_order,
            agent_registry=build_agent_registry(),
        )

        add_message(
            message_id=uuid.uuid4().hex,
            conversation_id=turn.conversation_id,
            role="ageix",
            content=json.dumps(result.get("deliverable", result), indent=2),
            metadata={
                "intent": "change_plan",
                "work_order_id": work_order.work_order_id,
                "artifact_id": result.get("artifact_id"),
                "evaluation": result.get("evaluation"),
            },
        )

        return {
            "conversation_id": turn.conversation_id,
            "turn": turn.model_dump(),
            "decision": decision.model_dump(),
            "work_order": work_order.__dict__,
            "result": result,
        }

    except Exception as e:
        return {
            "error": {
                "message": str(e),
                "type": "server_error",
                "trace": traceback.format_exc(),
            }
        }
    

@app.get("/v1/ageix/collaboration/{conversation_id}/turns")
def get_collaboration_turns(conversation_id: str, limit: int = 50):
    try:
        messages = get_messages(conversation_id, limit=limit)

        turns = []
        for msg in messages:
            metadata = msg.get("metadata", {})

            turns.append({
                "conversation_id": conversation_id,
                "speaker": msg.get("role"),
                "target": metadata.get("target"),
                "intent": metadata.get("intent", "discussion"),
                "content": msg.get("content"),
                "metadata": metadata,
                "created_at": msg.get("created_at"),
            })

        return {
            "conversation_id": conversation_id,
            "turn_count": len(turns),
            "turns": turns,
        }

    except Exception as e:
        return {
            "error": {
                "message": str(e),
                "type": "server_error",
                "trace": traceback.format_exc(),
            }
        }