import json
import os
from typing import List

from ..core.question import Question

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'data')
QUESTIONS_FILE = os.path.abspath(os.path.join(DATA_DIR, 'questions.json'))


class QuestionService:
    def __init__(self):
        os.makedirs(os.path.dirname(QUESTIONS_FILE), exist_ok=True)
        if not os.path.exists(QUESTIONS_FILE):
            # initialize with sample questions
            sample = [
                {
                    "id": "q1",
                    "prompt": "What is 1/2 + 1/4?",
                    "options": ["3/4", "1/4", "2/3", "5/8"],
                    "answer": "3/4"
                },
                {
                    "id": "q2",
                    "prompt": "What is 3/5 of 20?",
                    "options": ["12", "8", "15", "10"],
                    "answer": "12"
                },
                {
                    "id": "q3",
                    "prompt": "Which is greater?",
                    "options": ["2/3", "3/5", "4/7", "5/9"],
                    "answer": "2/3"
                },
                {
                    "id": "q4",
                    "prompt": "Simplify 6/8",
                    "options": ["3/4", "2/3", "4/6", "6/10"],
                    "answer": "3/4"
                },
                {
                    "id": "q5",
                    "prompt": "1/3 + 1/6 = ?",
                    "options": ["1/2", "2/3", "4/9", "5/6"],
                    "answer": "1/2"
                },
                {
                    "id": "q6",
                    "prompt": "What is 7/8 - 1/4?",
                    "options": ["5/8", "3/8", "1/2", "7/12"],
                    "answer": "5/8"
                }
            ]
            with open(QUESTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(sample, f, indent=2)

    def load_questions(self) -> List[Question]:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        return [Question(**q) for q in raw]

    def save_questions(self, questions):
        # questions: List[Question] | List[dict]
        data = []
        for q in questions:
            if isinstance(q, Question):
                data.append({
                    'id': q.id,
                    'prompt': q.prompt,
                    'options': q.options,
                    'answer': q.answer,
                })
            else:
                data.append(q)
        with open(QUESTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
