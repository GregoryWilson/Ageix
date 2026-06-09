def plan_task(task: dict) -> dict:
    title = task.get("title", "")
    description = task.get("description", "")
    text = f"{title} {description}".lower()

    subtasks = []

    if any(term in text for term in ["code", "implement", "routing", "api", "endpoint", "function", "python"]):
        subtasks.extend([
            {
                "title": f"Review current implementation for: {title}",
                "description": "Inspect relevant source files and identify the minimal safe change.",
                "priority": "normal",
                "owner": "planner",
            },
            {
                "title": f"Implement code changes for: {title}",
                "description": description,
                "priority": "normal",
                "owner": "coder",
            },
            {
                "title": f"Validate implementation for: {title}",
                "description": "Run compile checks and API tests to confirm behavior.",
                "priority": "normal",
                "owner": "tester",
            },
        ])
    else:
        subtasks.extend([
            {
                "title": f"Clarify objective for: {title}",
                "description": description,
                "priority": "normal",
                "owner": "planner",
            },
            {
                "title": f"Execute task: {title}",
                "description": description,
                "priority": "normal",
                "owner": "user",
            },
            {
                "title": f"Review result for: {title}",
                "description": "Confirm the task is complete and update status.",
                "priority": "normal",
                "owner": "chair",
            },
        ])

    return {
        "task_id": task.get("id"),
        "objective": title,
        "summary": f"Generated {len(subtasks)} subtasks for task: {title}",
        "subtasks": subtasks,
    }