from orchestration.state import Task


def validate_dependencies(tasks: list[dict]) -> None:
    validated = [Task.model_validate(t) for t in tasks]
    by_id = {task.id: task for task in validated}
    if len(by_id) != len(tasks):
        raise ValueError("Duplicate task IDs")
    required = {"REQ", "ARCH", "CODE", "TEST", "DOCS", "RELEASE"}
    if required != set(by_id):
        raise ValueError("Plan must contain REQ, ARCH, CODE, TEST, DOCS, and RELEASE tasks")
    critical = {"ARCH": "REQ", "CODE": "ARCH", "TEST": "CODE", "DOCS": "TEST", "RELEASE": "DOCS"}
    if any(dependency not in by_id[task].dependencies for task, dependency in critical.items()):
        raise ValueError("Plan omits a mandatory safety dependency")
    visiting, visited = set(), set()

    def visit(task_id):
        if task_id not in by_id:
            raise ValueError(f"Unknown task dependency {task_id}")
        if task_id in visiting:
            raise ValueError("Task dependency cycle")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in by_id[task_id].dependencies:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in by_id:
        visit(task_id)


def complete_task(tasks: list[dict], task_id: str) -> list[dict]:
    result = [dict(task) for task in tasks]
    by_id = {task["id"]: task for task in result}
    target = by_id[task_id]
    if any(by_id[dependency]["status"] != "completed" for dependency in target["dependencies"]):
        raise ValueError(f"Task {task_id} has incomplete dependencies")
    target["status"] = "completed"
    return result


def descendants(tasks: list[dict], sources: set[str]) -> set[str]:
    affected = set(sources)
    while True:
        expanded = affected | {task["id"] for task in tasks if set(task["dependencies"]) & affected}
        if expanded == affected:
            return affected
        affected = expanded
