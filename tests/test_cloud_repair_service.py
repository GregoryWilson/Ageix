from services.cloud_repair_service import CloudRepairService


class FakeCloudDevWorker:
    def generate_repair_proposal(self, escalation_packet, execution_target):
        assert execution_target == "cloud"
        return {
            "summary": "Cloud repair proposal",
            "changed_files": ["foo.py"],
        }


class BrokenCloudDevWorker:
    def generate_repair_proposal(self, escalation_packet, execution_target):
        raise RuntimeError("cloud unavailable")


def test_cloud_repair_service_returns_unavailable_without_worker():
    svc = CloudRepairService()

    result = svc.execute_cloud_repair({"objective": "Fix it"})

    assert result["status"] == "unavailable"
    assert result["proposal"] is None


def test_cloud_repair_service_returns_generated_proposal():
    svc = CloudRepairService(dev_worker=FakeCloudDevWorker())

    result = svc.execute_cloud_repair({"objective": "Fix it"})

    assert result["status"] == "proposal_generated"
    assert result["proposal"]["summary"] == "Cloud repair proposal"


def test_cloud_repair_service_handles_cloud_worker_failure():
    svc = CloudRepairService(dev_worker=BrokenCloudDevWorker())

    result = svc.execute_cloud_repair({"objective": "Fix it"})

    assert result["status"] == "unavailable"
    assert result["proposal"] is None
    assert "cloud unavailable" in result["reason"]