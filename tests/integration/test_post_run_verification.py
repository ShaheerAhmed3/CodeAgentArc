import json
import sys

from code_agent.generation import verify_existing


def test_completed_run_can_be_independently_reverified(tmp_path):
    output = tmp_path / "generated/demo"
    (output / ".codeagent").mkdir(parents=True)
    (output / "README.md").write_text("Demo\n", encoding="utf-8")
    (output / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")
    (output / "src").mkdir()
    (output / "src/app.js").write_text("export const ready = true;\n", encoding="utf-8")
    (output / "test").mkdir()
    (output / "test/app.test.js").write_text("// test\n", encoding="utf-8")
    report_path = output / ".codeagent/generation_report.json"
    report_path.write_text(json.dumps({"success": False, "stop_reason": "final_response",
                                       "error": None, "validation": {"success": False}}), encoding="utf-8")
    (output / ".codeagent/run.jsonl").write_text('{"event":"run_end"}\n', encoding="utf-8")
    assert verify_existing(project_root=tmp_path, output=output,
                           command=[sys.executable, "-c", "print('verified')"])
    result = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["success"] is True
    assert result["initial_success"] is False
    assert result["initial_validation"] == {"success": False}
    assert result["post_run_verification"] is True
    assert result["verification"][0]["success"] is True
    assert '"event": "post_run_verification"' in (output / ".codeagent/run.jsonl").read_text()
