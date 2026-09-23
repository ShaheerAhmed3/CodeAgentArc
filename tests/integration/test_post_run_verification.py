import json
import sys

from code_agent.generation import verify_existing


def test_completed_run_can_be_independently_reverified(tmp_path):
    output = tmp_path / "generated/demo"
    (output / ".codeagent").mkdir(parents=True)
    (output / "README.md").write_text(
        "Demo\n\n```sh\npython main.py\n```\n\n```sh\npython -m unittest discover -s tests\n```\n",
        encoding="utf-8",
    )
    (output / "requirements.txt").write_text("# standard library only\n", encoding="utf-8")
    (output / "main.py").write_text(
        "class Game:\n def start_game(self): self.question = 1\n def check_answer(self, answer): self.score = 1\n def finish_game(self): self.game_over = True\ndef main():\n import tkinter as tk\n tk.Tk().mainloop()\nif __name__ == '__main__': main()\n",
        encoding="utf-8",
    )
    (output / "tests").mkdir()
    (output / "tests/test_game.py").write_text(
        "def test_game_answer_score():\n from main import Game\n game = Game(); game.start_game(); game.check_answer(1); assert game.score == 1\n",
        encoding="utf-8",
    )
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
