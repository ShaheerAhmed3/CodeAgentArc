from dataclasses import dataclass, field
from typing import List, Optional

from .question import Question


class GameState:
    PLAYING = "Playing"
    PAUSED = "Paused"
    GAME_OVER = "GameOver"


@dataclass
class Game:
    questions: List[Question]
    score: int = 0
    index: int = 0
    state: str = GameState.PLAYING

    def current_question(self) -> Optional[Question]:
        if 0 <= self.index < len(self.questions):
            return self.questions[self.index]
        return None

    def submit_answer(self, answer: str) -> bool:
        if self.state != GameState.PLAYING:
            return False
        q = self.current_question()
        if q is None:
            return False
        correct = q.is_correct(answer)
        if correct:
            self.score += 1
            self.index += 1
            if self.index >= len(self.questions):
                self.state = GameState.GAME_OVER
        # On incorrect, stay on the same question to allow retry
        return correct

    def pause(self):
        if self.state == GameState.PLAYING:
            self.state = GameState.PAUSED

    def resume(self):
        if self.state == GameState.PAUSED:
            self.state = GameState.PLAYING

    def is_game_over(self) -> bool:
        return self.state == GameState.GAME_OVER

    def total_questions(self) -> int:
        return len(self.questions)
