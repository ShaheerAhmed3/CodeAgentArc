from .question import Question


def build_feedback_for_submission(question: Question, correct: bool) -> str:
    """
    Pure helper to build user-facing feedback text for a submission.
    Using the question object passed ensures the feedback always refers to the
    question that was actually answered, regardless of index movement.
    """
    return "Correct!" if correct else f"Incorrect. Correct answer: {question.answer}"
