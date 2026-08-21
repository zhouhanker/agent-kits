"""Deterministic CLI and transaction tests using isolated temporary roots."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from agent_kits.application.service import run_component_create, run_install, run_source_intake, run_update_cli
from agent_kits.infrastructure.agents import AgentAnalysis, LocalAgent, _agent_failure_message, _claude_command
from agent_kits.infrastructure.components import luna_candidate_sha256, luna_source_sha256
from agent_kits.infrastructure.state import state_file, write_json_atomic
from agent_kits.cli.main import main
from agent_kits.domain.errors import ConflictError, PolicyError
from agent_kits.infrastructure.repository import list_kits, list_source_locks
from agent_kits.infrastructure.sources import quarantine_source


REPOSITORY = Path(__file__).resolve().parents[1]


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name) / "project"
        self.project.mkdir()
        self.state = Path(self.temp_dir.name) / "state"
        self.state.mkdir()
        self.codex = Path(self.temp_dir.name) / "codex"
        self.claude = Path(self.temp_dir.name) / "claude"
        self.old_environment = os.environ.copy()
        os.environ["AGENT_KITS_STATE_ROOT"] = str(self.state / "user")
        os.environ["AGENT_KITS_CODEX_USER_ROOT"] = str(self.codex)
        os.environ["AGENT_KITS_CLAUDE_CODE_USER_ROOT"] = str(self.claude)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.old_environment)
        self.temp_dir.cleanup()

    def invoke(self, *arguments: str) -> tuple[int, dict[str, object], str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--repository", str(REPOSITORY), "--project-root", str(self.project), "--json", *arguments])
        output = stdout.getvalue().strip()
        return code, json.loads(output) if output else {}, output, stderr.getvalue()

    def test_catalog_and_source_lock_are_validated(self) -> None:
        kits = list_kits(REPOSITORY)
        locks = list_source_locks(REPOSITORY)
        self.assertEqual([kit.identifier for kit in kits], ["base", "luna-worker"])
        self.assertEqual(locks[0].install_policy, "manual-only")
        code, result, _, _ = self.invoke("catalog", "list")
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])

    def test_source_import_quarantines_without_execution(self) -> None:
        document = self.project / "guide.md"
        document.write_text("# Guide\n\n```sh\ntouch SHOULD_NOT_EXIST\n```\n", encoding="utf-8")
        code, result, _, _ = self.invoke("source", "import", str(document), "--as", "document")
        self.assertEqual(code, 0)
        self.assertFalse((self.project / "SHOULD_NOT_EXIST").exists())
        self.assertTrue(Path(result["data"]["metadata"]).is_file())

    def test_project_plan_apply_verify_and_rollback(self) -> None:
        code, result, _, _ = self.invoke("plan", "--kit", "base", "--scope", "project", "--client", "codex")
        self.assertEqual(code, 0)
        plan_id = result["data"]["plan_id"]
        code, _, _, _ = self.invoke("apply", "--plan", plan_id, "--scope", "project")
        self.assertEqual(code, 5)
        code, result, _, _ = self.invoke("apply", "--plan", plan_id, "--scope", "project", "--yes")
        self.assertEqual(code, 0)
        receipt_id = result["data"]["receipt_id"]
        target = self.project / "AGENTS.md"
        self.assertTrue(target.is_file())
        code, result, _, _ = self.invoke("verify", "--receipt", receipt_id, "--scope", "project")
        self.assertEqual(code, 0)
        self.assertTrue(result["data"]["verified"])
        first_content = target.read_text(encoding="utf-8")
        code, result, _, _ = self.invoke("plan", "--kit", "base", "--scope", "project", "--client", "codex")
        self.assertEqual(code, 0)
        code, _, _, _ = self.invoke("apply", "--plan", result["data"]["plan_id"], "--scope", "project", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(target.read_text(encoding="utf-8"), first_content)
        code, result, _, _ = self.invoke("rollback", "--receipt", receipt_id, "--scope", "project", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(result["data"]["status"], "rolled_back")
        self.assertFalse(target.exists())

    def test_apply_refuses_target_changed_after_plan(self) -> None:
        code, result, _, _ = self.invoke("plan", "--kit", "base", "--scope", "project", "--client", "codex")
        self.assertEqual(code, 0)
        (self.project / "AGENTS.md").write_text("user change\n", encoding="utf-8")
        code, result, _, _ = self.invoke("apply", "--plan", result["data"]["plan_id"], "--scope", "project", "--yes")
        self.assertEqual(code, 4)
        self.assertIn("Target changed", result["error"]["message"])

    def test_user_scope_uses_overrideable_client_root(self) -> None:
        code, result, _, _ = self.invoke("plan", "--kit", "base", "--scope", "user", "--client", "claude-code")
        self.assertEqual(code, 0)
        code, result, _, _ = self.invoke("apply", "--plan", result["data"]["plan_id"], "--scope", "user", "--yes")
        self.assertEqual(code, 0)
        self.assertTrue((self.claude / "CLAUDE.md").is_file())

    def test_http_policy_rejects_plain_http(self) -> None:
        code, result, _, _ = self.invoke("source", "inspect", "http://example.com")
        self.assertEqual(code, 5)
        self.assertEqual(result["error"]["type"], "PolicyError")

    def test_explicit_file_source_selector(self) -> None:
        document = self.project / "guide.md"
        document.write_text("# Guide\n", encoding="utf-8")
        code, result, _, _ = self.invoke("source", "inspect", "--file", str(document))
        self.assertEqual(code, 0)
        self.assertEqual(result["data"]["source_type"], "file")

    def test_single_dash_file_selector_is_supported(self) -> None:
        document = self.project / "guide.md"
        document.write_text("# Guide\n", encoding="utf-8")
        code, result, _, _ = self.invoke("source", "inspect", "-file", str(document))
        self.assertEqual(code, 0)
        self.assertEqual(result["data"]["source_type"], "file")

    def test_agents_list_is_read_only(self) -> None:
        code, result, _, _ = self.invoke("agents", "list")
        self.assertEqual(code, 0)
        self.assertIn("agents", result["data"])
        self.assertIn("sandboxes", result["data"])
        self.assertTrue(all(agent["model_access"] == "not_checked" for agent in result["data"]["agents"]))

    def test_agents_check_proves_model_access_without_installing(self) -> None:
        analysis = AgentAnalysis("codex", "unsupported", "Fixed capability probe", "low", False)
        agent = LocalAgent("codex", ("codex",), "/usr/local/bin/codex", True)
        with mock.patch("agent_kits.infrastructure.agents.select_agent", return_value=agent), mock.patch(
            "agent_kits.infrastructure.agents.analyze_source", return_value=analysis
        ) as analyze:
            code, result, _, _ = self.invoke("agents", "check", "--agent", "codex")
        self.assertEqual(code, 0)
        self.assertEqual(result["data"]["agent"], "codex")
        self.assertEqual(result["data"]["model_access"], "available")
        self.assertFalse((self.codex / "config.toml").exists())
        analyze.assert_called_once()

    def test_claude_subscription_analysis_does_not_require_api_key_mode(self) -> None:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("AGENT_KITS_CLAUDE_CODE_MODE", None)
        command = _claude_command(LocalAgent("claude-code", ("claude",), "/usr/local/bin/claude", True), "probe")
        self.assertNotIn("--bare", command)
        self.assertIn("--tools", command)
        self.assertIn("--strict-mcp-config", command)
        self.assertIn("--disable-slash-commands", command)

    def test_claude_api_key_mode_uses_bare_execution(self) -> None:
        os.environ["AGENT_KITS_CLAUDE_CODE_MODE"] = "api-key"
        command = _claude_command(LocalAgent("claude-code", ("claude",), "/usr/local/bin/claude", True), "probe")
        self.assertIn("--bare", command)

    def test_agent_failure_message_prefers_structured_error_and_redacts_key(self) -> None:
        stdout = json.dumps({"result": "Request rejected for sk-secret_value"})
        self.assertEqual(_agent_failure_message("ignored", stdout), "Request rejected for sk-***")

    def test_luna_install_requires_validation_receipt(self) -> None:
        code, result, _, _ = self.invoke("install", "luna-worker", "--scope", "user", "--yes")
        self.assertEqual(code, 5)
        self.assertIn("validation receipt", result["error"]["message"])
        self.assertFalse((self.codex / "agents" / "luna-worker.toml").exists())

    def test_luna_install_applies_only_to_isolated_user_root_after_receipt(self) -> None:
        receipt = {
            "schema_version": 1,
            "receipt_id": "luna-validated",
            "component_id": "luna-worker",
            "source_sha256": luna_source_sha256(REPOSITORY),
            "candidate_sha256": luna_candidate_sha256(REPOSITORY),
            "agent": "codex",
            "sandbox_backend": "docker",
            "status": "validated",
        }
        write_json_atomic(state_file(self.state / "user", "validations", receipt["receipt_id"]), receipt)
        result = run_install(REPOSITORY, self.project, "luna-worker", "user", True)
        self.assertTrue(result["installed"])
        self.assertTrue((self.codex / "agents" / "luna-worker.toml").is_file())
        self.assertTrue((self.codex / "hooks" / "enforce-luna-worker.py").is_file())
        self.assertIn("agent-kits:luna-worker", (self.codex / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("hooks = true", (self.codex / "config.toml").read_text(encoding="utf-8"))
        self.assertIn("luna_worker", (self.codex / "AGENTS.md").read_text(encoding="utf-8"))

    def test_source_intake_fails_before_agent_when_sandbox_is_missing(self) -> None:
        guide = REPOSITORY / "docs" / "CODEX_LUNA_WORKER_SETUP.md"
        with mock.patch("agent_kits.application.service.select_sandbox", side_effect=PolicyError("no sandbox")), mock.patch(
            "agent_kits.application.service.select_agent"
        ) as select_agent:
            with self.assertRaises(PolicyError):
                run_source_intake(REPOSITORY, str(guide), "codex", "user", self.project)
        select_agent.assert_not_called()

    def test_component_create_records_candidate_without_client_install(self) -> None:
        intake = {
            "inspection": {"source": "guide.md", "sha256": "a" * 64},
            "analysis": {"agent": "codex", "kind": "mcp", "summary": "MCP candidate", "risk": "medium", "requires_dynamic_validation": True},
            "component_id": None,
            "installable": False,
        }
        with mock.patch("agent_kits.application.service.run_source_intake", return_value=intake):
            result = run_component_create(REPOSITORY, self.project, "guide.md", "codex", "mcp-candidate")
        self.assertFalse(result["installable"])
        candidate = Path(result["path"])
        self.assertTrue(candidate.is_file())
        self.assertEqual(json.loads(candidate.read_text(encoding="utf-8"))["status"], "review_required")
        self.assertFalse((self.codex / "config.toml").exists())

    def test_known_luna_source_resolves_only_after_agent_analysis(self) -> None:
        guide = REPOSITORY / "docs" / "CODEX_LUNA_WORKER_SETUP.md"
        with mock.patch("agent_kits.application.service.select_sandbox"), mock.patch("agent_kits.application.service.select_agent", return_value=LocalAgent("codex", ("codex",), "/bin/true", True)), mock.patch(
            "agent_kits.application.service.analyze_source",
            return_value=AgentAnalysis("codex", "codex_subagent", "Luna setup guide", "high", True),
        ), mock.patch(
            "agent_kits.application.service.validate_luna_worker",
            return_value={"receipt_id": "validated", "component_id": "luna-worker", "status": "validated"},
        ):
            result = run_source_intake(REPOSITORY, str(guide), "codex", "user", self.project)
        self.assertTrue(result["installable"])
        self.assertEqual(result["component_id"], "luna-worker")

    def test_source_intake_without_confirmation_keeps_validated_component_uninstalled(self) -> None:
        intake = {"installable": True, "component_id": "luna-worker", "validation": {"receipt_id": "validated"}}
        with mock.patch("agent_kits.cli.main.run_source_intake", return_value=intake), mock.patch(
            "agent_kits.cli.main.run_install"
        ) as install:
            code, result, _, _ = self.invoke("--non-interactive", "source", "intake", "--file", "guide.md", "--scope", "user")
        self.assertEqual(code, 0)
        self.assertFalse(result["data"]["installation"]["installed"])
        self.assertEqual(result["data"]["installation"]["status"], "not_installed")
        install.assert_not_called()

    def test_source_selector_requires_one_input(self) -> None:
        code, result, _, _ = self.invoke("source", "inspect")
        self.assertEqual(code, 2)
        self.assertEqual(result, {})

    def test_cli_update_requires_official_installer_metadata(self) -> None:
        missing = self.state / "missing-install.json"
        os.environ["KITCLI_INSTALL_STATE"] = str(missing)
        code, result, _, _ = self.invoke("update", "--yes")
        self.assertEqual(code, 3)
        self.assertEqual(result["error"]["type"], "ValidationError")

    def test_cli_update_defaults_to_read_only_check(self) -> None:
        missing = self.state / "missing-install.json"
        os.environ["KITCLI_INSTALL_STATE"] = str(missing)
        code, result, _, _ = self.invoke("update")
        self.assertEqual(code, 3)
        self.assertEqual(result["error"]["type"], "ValidationError")

    def test_official_update_check_verifies_release_wheel(self) -> None:
        wheel_name = "agent_kits-9.9.9-py3-none-any.whl"
        wheel = self.state / wheel_name
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("agent_kits-9.9.9.dist-info/METADATA", "Metadata-Version: 2.1\nVersion: 9.9.9\n")
        import hashlib

        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        checksums = self.state / "SHA256SUMS"
        checksums.write_text(f"{digest}  {wheel_name}\n", encoding="utf-8")
        metadata = {
            "schema_version": 1,
            "method": "official-isolated-installer",
            "package": "agent-kits",
            "python": sys.executable,
            "install_root": str(Path(sys.executable).resolve().parents[2]),
            "wheel_url": f"https://example.invalid/{wheel_name}",
            "checksum_url": "https://example.invalid/SHA256SUMS",
        }
        state_path = self.state / "install.json"
        state_path.write_text(json.dumps(metadata), encoding="utf-8")
        os.environ["KITCLI_INSTALL_STATE"] = str(state_path)

        def copy_asset(url: str, destination: Path) -> None:
            destination.write_bytes(wheel.read_bytes() if url.endswith(".whl") else checksums.read_bytes())

        with mock.patch("agent_kits.application.service._download_update_asset", side_effect=lambda url, destination, max_bytes: copy_asset(url, destination)):
            result = run_update_cli(check_only=True)
        self.assertTrue(result["update_available"])
        self.assertEqual(result["available_version"], "9.9.9")

    def test_bundle_path_traversal_is_rejected(self) -> None:
        bundle = self.project / "unsafe.zip"
        with zipfile.ZipFile(bundle, "w") as archive:
            archive.writestr("../escape.txt", "blocked")
        code, result, _, _ = self.invoke("source", "import", str(bundle), "--as", "bundle")
        self.assertEqual(code, 5)
        self.assertEqual(result["error"]["type"], "PolicyError")

    def test_target_symlink_is_rejected_before_plan(self) -> None:
        outside = Path(self.temp_dir.name) / "outside.md"
        outside.write_text("must remain unchanged\n", encoding="utf-8")
        try:
            (self.project / "AGENTS.md").symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlink creation is unavailable on this runner: {error}")
        code, result, _, _ = self.invoke("plan", "--kit", "base", "--scope", "project", "--client", "codex")
        self.assertEqual(code, 5)
        self.assertEqual(result["error"]["type"], "PolicyError")
        self.assertEqual(outside.read_text(encoding="utf-8"), "must remain unchanged\n")

    def test_tampered_receipt_is_rejected(self) -> None:
        code, result, _, _ = self.invoke("plan", "--kit", "base", "--scope", "project", "--client", "codex")
        self.assertEqual(code, 0)
        code, result, _, _ = self.invoke("apply", "--plan", result["data"]["plan_id"], "--scope", "project", "--yes")
        self.assertEqual(code, 0)
        receipt_path = self.project / ".agent-kits" / "receipts" / f"{result['data']['receipt_id']}.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["status"] = "tampered"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        code, result, _, _ = self.invoke("verify", "--receipt", receipt["receipt_id"], "--scope", "project")
        self.assertEqual(code, 3)
        self.assertEqual(result["error"]["type"], "ValidationError")


if __name__ == "__main__":
    unittest.main()
