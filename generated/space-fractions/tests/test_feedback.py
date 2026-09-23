from space_fractions.core.question import Question
from space_fractions.core.feedback import build_feedback_for_submission


def test_wrong_first_answer_reports_first_question_answer_not_last():
    # Distinct answers to ensure we don't accidentally match the last
    q1 = Question(id="q1", prompt="p1", options=["a1", "b1"], answer="a1")
    qlast = Question(id="q_last", prompt="pN", options=["z", "y"], answer="z")

    # Simulate answering the first question incorrectly
    msg = build_feedback_for_submission(q1, correct=False)

    assert "Incorrect." in msg
    assert q1.answer in msg
    assert qlast.answer not in msg


def test_feedback_helper_correct_message():
    q = Question(id="q2", prompt="p2", options=["x"], answer="x")
    assert build_feedback_for_submission(q, correct=True) == "Correct!"
