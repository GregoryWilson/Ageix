import json
from agents.planner_agent import execute_planner_agent

task = {
    "title": "Sprint 6 Planner Integration",
    "description": "Design implementation plan for planner integration."
}

result = execute_planner_agent(task=task)

print("\n=== PLANNER RESULT ===\n")
print(json.dumps(result, indent=2))