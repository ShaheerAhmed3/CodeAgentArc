from dataclasses import dataclass
from typing import List


@dataclass
class Question:
    id: str
    prompt: str
    options: List[str]
    answer: str  # correct answer string

    def is_correct(self, selected: str) -> bool:
        return selected.strip() == self.answer.strip()
