import sqlite3
import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional
from unittest import result

DB_PATH = Path("ageix.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_runs (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            input_json TEXT,
            output_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS project_state (
            conversation_id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        )
        """)


def now_iso():
    return datetime.now(UTC).isoformat()


def create_conversation(conversation_id: str, title: Optional[str] = None):
    ts = now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO conversations
            (id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (conversation_id, title, ts, ts)
        )


def touch_conversation(conversation_id: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now_iso(), conversation_id)
        )


def add_message(message_id: str, conversation_id: str, role: str, content: str, metadata: Optional[dict] = None):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO messages
            (id, conversation_id, role, content, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                conversation_id,
                role,
                content,
                json.dumps(metadata or {}),
                now_iso()
            )
        )
    touch_conversation(conversation_id)


def get_messages(conversation_id: str, limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT role, content, metadata_json, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (conversation_id, limit)
        ).fetchall()

    return [
        {
            "role": row["role"],
            "content": row["content"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": row["created_at"],
        }
        for row in rows
    ]

def get_project_state(conversation_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT state_json
            FROM project_state
            WHERE conversation_id = ?
            """,
            (conversation_id,)
        ).fetchone()

    if not row:
        return {}

    return json.loads(row["state_json"] or "{}")


def set_project_state(conversation_id: str, state: dict):
    ts = now_iso()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO project_state
            (conversation_id, state_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(conversation_id)
            DO UPDATE SET
                state_json = excluded.state_json,
                updated_at = excluded.updated_at
            """,
            (
                conversation_id,
                json.dumps(state),
                ts
            )
        )

def create_task(
    task_id: str,
    conversation_id: str,
    title: str,
    description: str = "",
    priority: str = "normal",
    owner: str = "user",
    parent_task_id: str | None = None
) -> dict | None:
    ts = now_iso()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO tasks
            (id, conversation_id, title, description, status, priority, owner, created_at, updated_at, parent_task_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, conversation_id, title, description, "new", priority, owner, ts, ts, parent_task_id)        )

    add_task_event(task_id, "created", {
        "title": title,
        "description": description,
        "priority": priority,
        "owner": owner,
        "parent_task_id": parent_task_id,
    })

    return get_task(task_id)


def get_task(task_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,)
        ).fetchone()

    return dict(row) if row else None


def list_tasks(conversation_id: str | None = None) -> list[dict]:
    with get_conn() as conn:
        if conversation_id:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE conversation_id = ? ORDER BY created_at DESC",
                (conversation_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC"
            ).fetchall()

    return [dict(row) for row in rows]


def update_task(task_id: str, updates: dict) -> dict | None:
    allowed = {"title", "description", "status", "priority", "owner"}
    updates = {k: v for k, v in updates.items() if k in allowed and v is not None}

    if not updates:
        return get_task(task_id)

    updates["updated_at"] = now_iso()

    set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
    values = list(updates.values())
    values.append(task_id)

    with get_conn() as conn:
        conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ?",
            values
        )

    add_task_event(task_id, "updated", updates)

    return get_task(task_id)


def add_task_event(task_id: str, event_type: str, event_data: dict):
    import uuid

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO task_events
            (id, task_id, event_type, event_data_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                task_id,
                event_type,
                json.dumps(event_data or {}),
                now_iso()
            )
        )


def get_task_events(task_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM task_events
            WHERE task_id = ?
            ORDER BY created_at ASC
            """,
            (task_id,)
        ).fetchall()

    events = []
    for row in rows:
        event = dict(row)
        event["event_data"] = json.loads(event.pop("event_data_json") or "{}")
        events.append(event)

    return events


def get_child_tasks(parent_task_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM tasks
            WHERE parent_task_id = ?
            ORDER BY created_at ASC
            """,
            (parent_task_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def get_task_tree(task_id: str) -> dict | None:
    task = get_task(task_id)

    if not task:
        return None

    children = get_child_tasks(task_id)

    return {
        "task": task,
        "events": get_task_events(task_id),
        "children": [
            get_task_tree(child["id"])
            for child in children
        ]
    }

def flatten_task_tree(tree: dict) -> list[dict]:
    tasks = [tree["task"]]

    for child in tree.get("children", []):
        tasks.extend(flatten_task_tree(child))

    return tasks


def get_task_status_summary(task_id: str) -> dict | None:
    tree = get_task_tree(task_id)

    if not tree:
        return None

    all_tasks = flatten_task_tree(tree)
    child_tasks = all_tasks[1:]

    progress = {
        "total": len(child_tasks),
        "new": 0,
        "planned": 0,
        "in_progress": 0,
        "blocked": 0,
        "completed": 0,
        "cancelled": 0,
    }

    for task in child_tasks:
        status = task.get("status", "new")
        progress[status] = progress.get(status, 0) + 1

    next_actions = []

    blocked = [t for t in child_tasks if t.get("status") == "blocked"]
    in_progress = [t for t in child_tasks if t.get("status") == "in_progress"]
    new = [t for t in child_tasks if t.get("status") == "new"]

    if blocked:
        next_actions.append(f"Resolve blocked task: {blocked[0]['title']}")
    elif in_progress:
        next_actions.append(f"Continue in-progress task: {in_progress[0]['title']}")
    elif new:
        next_actions.append(f"Start next task: {new[0]['title']}")
    elif child_tasks and progress["completed"] == len(child_tasks):
        next_actions.append("All child tasks are complete. Review and close the parent task.")
    else:
        next_actions.append("No child tasks found. Plan this task or add subtasks.")

    parent = tree["task"]

    result = {
        "task_id": parent["id"],
        "title": parent["title"],
        "status": parent["status"],
        "owner": parent["owner"],
        "priority": parent["priority"],
        "progress": progress,
        "next_actions": next_actions,
    }

    return result


def get_next_action_task(parent_task_id: str) -> dict | None:
    children = get_child_tasks(parent_task_id)

    for status in ["blocked", "in_progress", "new", "planned"]:
        for task in children:
            if task.get("status") == status:
                return task

    return None


def add_agent_turn(
    turn_id: str,
    task_id: str,
    conversation_id: str,
    agent_name: str,
    content: str,
    visibility: str = "internal",
    turn_type: str = "comment",
    metadata: dict | None = None
):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO agent_turns
            (id, task_id, conversation_id, agent_name, visibility, turn_type, content, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn_id,
                task_id,
                conversation_id,
                agent_name,
                visibility,
                turn_type,
                content,
                json.dumps(metadata or {}),
                now_iso()
            )
        )


def get_agent_turns(task_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM agent_turns
            WHERE task_id = ?
            ORDER BY created_at ASC
            """,
            (task_id,)
        ).fetchall()

    turns = []
    for row in rows:
        turn = dict(row)
        turn["metadata"] = json.loads(turn.pop("metadata_json") or "{}")
        turns.append(turn)

    return turns

def get_sibling_tasks(task: dict) -> list[dict]:
    parent_task_id = task.get("parent_task_id")

    if not parent_task_id:
        return []

    siblings = get_child_tasks(parent_task_id)

    return [
        sibling
        for sibling in siblings
        if sibling.get("id") != task.get("id")
    ]