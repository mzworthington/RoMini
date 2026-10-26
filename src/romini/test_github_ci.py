from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ci_workflow_can_force_a_release_from_workflow_dispatch() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "force_release:" in workflow
    assert "force_level:" in workflow
    assert "force-level:" in workflow
    assert "github.event.inputs.force_release" in workflow


def test_main_deploys_the_demo_worker_after_verify() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "deploy-demo:" in workflow
    assert "needs: verify" in workflow
    assert "https://demo.romini.party" in workflow
    assert "uv run pywrangler d1 migrations apply romini-demo --remote" in workflow
    assert "uv run pywrangler deploy" in workflow
    assert "CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID" in workflow
    assert "secrets.POSTHOG_TOKEN" in workflow
    assert "pywrangler secret put POSTHOG_TOKEN" in workflow
    assert "https://a.mzworthington.co.uk" in workflow


def test_pulumi_cloudflare_workflow_calls_edge_dns() -> None:
    workflow = (ROOT / ".github" / "workflows" / "pulumi-cloudflare.yml").read_text()

    assert "mzworthington/edge-dns/.github/workflows/product-pulumi-cloudflare.yml@main" in workflow
    assert "work-dir: infra/cloudflare" in workflow
    assert "stack-name: prod" in workflow
    assert "environment-url: https://demo.romini.party" in workflow
    assert "secrets: inherit" in workflow


def test_party_deploy_fails_when_cloudflare_credentials_are_missing() -> None:
    workflow = (ROOT / ".github" / "workflows" / "party.yml").read_text()

    assert "https://romini.party" in workflow
    assert "CLOUDFLARE_ACCOUNT_ID" in workflow
    assert "Skipping wrangler deploy" not in workflow
    assert "exit 1" in workflow
    assert "secrets.POSTHOG_TOKEN" in workflow
    assert "public/posthog-config.json" in workflow
    assert "https://a.mzworthington.co.uk" in workflow
    assert "phc_" not in workflow
