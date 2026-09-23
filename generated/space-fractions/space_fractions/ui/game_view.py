import tkinter as tk
from tkinter import ttk, messagebox

from typing import Optional, List
from ..core.game import Game, GameState
from ..core.question import Question
from ..core.feedback import build_feedback_for_submission


class GameFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self['padding'] = (20, 20)

        self.header = ttk.Label(self, text="Play — Space Fractions", style='Header.TLabel')
        self.header.pack(pady=(10, 10))

        self.info = ttk.Label(self, text="Answer the question. Use 1–4 keys to select, Enter to submit. P to pause.")
        self.info.pack(pady=(0, 10))

        # Score and progress
        self.progress_var = tk.StringVar(value="Question 0/0 • Score: 0")
        self.progress = ttk.Label(self, textvariable=self.progress_var)
        self.progress.pack(pady=(0, 10))

        # Question prompt
        self.prompt_var = tk.StringVar(value="")
        self.prompt_label = ttk.Label(self, textvariable=self.prompt_var, wraplength=700, justify=tk.LEFT)
        self.prompt_label.pack(pady=(10, 10))

        # Options
        self.selected_var = tk.StringVar(value="")
        self.option_buttons = []
        for i in range(4):
            btn = ttk.Radiobutton(self, text=f"Option {i+1}", value=str(i), variable=self.selected_var)
            btn.pack(anchor='w', padx=20, pady=4)
            self.option_buttons.append(btn)

        self.feedback_var = tk.StringVar(value="")
        self.feedback_label = ttk.Label(self, textvariable=self.feedback_var)
        self.feedback_label.pack(pady=(6, 6))

        # Controls
        controls = ttk.Frame(self)
        controls.pack(pady=10)
        self.submit_btn = ttk.Button(controls, text="Submit", command=self.submit)
        self.pause_btn = ttk.Button(controls, text="Pause (P)", command=self.toggle_pause)
        self.menu_btn = ttk.Button(controls, text="Main Menu (Esc)", command=lambda: controller.show_frame("MainMenuFrame"))
        self.submit_btn.grid(row=0, column=0, padx=5)
        self.pause_btn.grid(row=0, column=1, padx=5)
        self.menu_btn.grid(row=0, column=2, padx=5)

        # Keyboard shortcuts
        for i in range(4):
            self.bind_all(str(i+1), lambda e, idx=i: self.choose_idx(idx))
        self.bind_all('<Return>', lambda e: self.submit())
        self.bind_all('p', lambda e: self.toggle_pause())
        self.bind_all('P', lambda e: self.toggle_pause())

        self.game: Optional[Game] = None
        self.current_options: List[str] = []

    def on_show(self):
        # Nothing special
        pass

    def start_new_game(self, questions):
        # questions: List[Question]
        self.game = Game(questions=list(questions))
        self.feedback_var.set("")
        self.next_question()

    def choose_idx(self, idx: int):
        if self.game and self.game.state == GameState.PAUSED:
            return
        if idx < len(self.option_buttons):
            self.option_buttons[idx].invoke()

    def submit(self):
        if not self.game:
            return
        if self.game.state == GameState.PAUSED:
            messagebox.showinfo("Paused", "Resume the game to submit an answer.")
            return
        sel = self.selected_var.get()
        if sel == "":
            messagebox.showwarning("No selection", "Please choose an option (1–4).")
            return
        try:
            idx = int(sel)
        except ValueError:
            return
        if idx >= len(self.current_options):
            return
        ans = self.current_options[idx]
        # Capture the question being answered before potentially advancing index
        answered_q = self.game.current_question()
        correct = self.game.submit_answer(ans)
        if answered_q is None:
            return
        self.feedback_var.set(build_feedback_for_submission(answered_q, correct))
        if self.game.is_game_over():
            self.finish_game()
        else:
            self.after(500, self.next_question)

    def toggle_pause(self):
        if not self.game:
            return
        if self.game.state == GameState.PAUSED:
            self.game.resume()
            self.pause_btn.config(text="Pause (P)")
            self.feedback_var.set("Resumed")
        elif self.game.state == GameState.PLAYING:
            self.game.pause()
            self.pause_btn.config(text="Resume (P)")
            self.feedback_var.set("Paused")
        self.update_progress()

    def next_question(self):
        if not self.game:
            return
        q = self.game.current_question()
        if not q:
            return
        self.prompt_var.set(q.prompt)
        self.current_options = list(q.options)
        # Update radio texts and values
        for i, btn in enumerate(self.option_buttons):
            if i < len(self.current_options):
                btn.config(text=f"{i+1}. {self.current_options[i]}", value=str(i), state=tk.NORMAL)
            else:
                btn.config(text=f"{i+1}.", value=str(i), state=tk.DISABLED)
        self.selected_var.set("")
        self.update_progress()

    def update_progress(self):
        if not self.game:
            return
        cur = min(self.game.index + (1 if self.game.state != GameState.GAME_OVER else 0), self.game.total_questions())
        self.progress_var.set(f"Question {cur}/{self.game.total_questions()} • Score: {self.game.score} • State: {self.game.state}")

    def finish_game(self):
        # Save last score and switch to Score frame with info
        if not self.game:
            return
        info = {
            'score': self.game.score,
            'total': self.game.total_questions(),
        }
        self.controller.save_last_score(info)
        score_frame = self.controller.frames["ScoreFrame"]
        score_frame.set_summary(final=True)
        self.controller.show_frame("ScoreFrame")
