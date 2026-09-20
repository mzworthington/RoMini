from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ci_workflow_can_force_a_release_from_workflow_dispatch() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "force_release:" in workflow
    assert "force_level:" in workflow
    assert "force-level:" in workflow
    assert "github.event.inputs.force_release" in workflow
