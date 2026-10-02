from unittest.mock import Mock

from cato_deal_intel.orchestration.services import RunArtifactService
from cato_deal_intel.repositories.contracts import ArtifactRepository


def test_run_artifact_service_delegates_failed_run() -> None:
    repository = Mock(spec=ArtifactRepository)
    service = RunArtifactService(repository)
    error = RuntimeError("agent failed")

    service.save_failed_run(
        run_id="run-1",
        opportunity_id="OPP-1001",
        user_id="USR-5001",
        traces=[],
        error=error,
    )

    repository.save_failure_trace.assert_called_once_with(
        run_id="run-1",
        opportunity_id="OPP-1001",
        user_id="USR-5001",
        traces=[],
        error=error,
    )
