from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/agent", tags=["read-only workflow observability"])


@router.get("/runs")
def runs(request: Request):
    return request.app.state.agent_store.list_runs()


@router.get("/metrics")
def metrics(request: Request):
    return request.app.state.agent_store.metrics()


@router.get("/runs/{run_id}")
def run(run_id: str, request: Request):
    result = request.app.state.agent_store.public_run(run_id)
    if result is None:
        raise HTTPException(404, "Workflow run not found")
    return result


@router.get("/runs/{run_id}/audit")
def audit(run_id: str, request: Request):
    if request.app.state.agent_store.public_run(run_id) is None:
        raise HTTPException(404, "Workflow run not found")
    return request.app.state.agent_store.audit_events(run_id)
