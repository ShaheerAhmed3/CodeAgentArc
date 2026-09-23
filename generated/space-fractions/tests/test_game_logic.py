import json
from space_fractions.core.game import Game, GameState
from space_fractions.core.question import Question


def sample_questions():
    return [
        Question(id="q1", prompt="1/2+1/2?", options=["1", "1/2", "2", "3/4"], answer="1"),
        Question(id="q2", prompt="Simplify 2/4", options=["1/2", "3/4", "2/4", "2/8"], answer="1/2"),
        Question(id="q3", prompt="3/5 of 10", options=["6", "5", "3", "7"], answer="6"),
    ]


def test_game_progression_and_scoring():
    g = Game(questions=sample_questions())
    assert g.state == GameState.PLAYING
    assert g.total_questions() == 3

    # Q1 correct
    assert g.current_question().prompt.startswith("1/2+1/2")
    assert g.submit_answer("1") is True
    assert g.score == 1
    assert g.state == GameState.PLAYING

    # Q2 wrong
    assert g.current_question().prompt.startswith("Simplify 2/4")
    assert g.submit_answer("3/4") is False
    assert g.score == 1

    # Pause/resume mid-game
    g.pause()
    assert g.state == GameState.PAUSED
    # Submitting while paused should not work and not change index/score
    assert g.submit_answer("1/2") is False
    assert g.state == GameState.PAUSED
    g.resume()
    assert g.state == GameState.PLAYING

    # Q2 still pending after resume; answer correctly now
    assert g.current_question().prompt.startswith("Simplify 2/4")
    assert g.submit_answer("1/2") is True
    assert g.score == 2

    # Q3 correct and complete
    assert g.current_question().prompt.startswith("3/5 of 10")
    assert g.submit_answer("6") is True
    assert g.score == 3
    assert g.is_game_over()


def test_game_over_state_blocks_answers():
    g = Game(questions=[Question(id="q1", prompt="p", options=["a"], answer="a")])
    assert g.submit_answer("a") is True
    assert g.is_game_over()
    # further submissions ignored
    assert g.submit_answer("a") is False
    assert g.score == 1
