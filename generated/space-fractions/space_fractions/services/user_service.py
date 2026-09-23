import json
import os
from typing import Optional

from ..core.user import User

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'data')
LAST_SCORE_FILE = os.path.abspath(os.path.join(DATA_DIR, 'last_score.json'))


class UserService:
    def __init__(self):
        self._user: Optional[User] = None
        os.makedirs(os.path.dirname(LAST_SCORE_FILE), exist_ok=True)

    @property
    def current_user(self) -> Optional[User]:
        return self._user

    def login(self, username: str, is_admin: bool = False):
        self._user = User(username=username, is_admin=is_admin)

    def logout(self):
        self._user = None

    def load_last_score(self):
        if os.path.exists(LAST_SCORE_FILE):
            try:
                with open(LAST_SCORE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def save_last_score(self, score_dict):
        with open(LAST_SCORE_FILE, 'w', encoding='utf-8') as f:
            json.dump(score_dict, f, indent=2)
