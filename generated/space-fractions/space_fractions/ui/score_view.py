from tkinter import ttk


class ScoreFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self['padding'] = (20, 20)

        self.header = ttk.Label(self, text="Score", style='Header.TLabel')
        self.header.pack(pady=(10, 10))

        self.summary_var = ttk.Label(self, text="No games played yet.")
        self.summary_var.pack(pady=(0, 10))

        btns = ttk.Frame(self)
        btns.pack(pady=10)
        ttk.Button(btns, text="Back to Menu", command=lambda: controller.show_frame("MainMenuFrame")).grid(row=0, column=0, padx=5)
        ttk.Button(btns, text="Play Again", command=self.play_again).grid(row=0, column=1, padx=5)

    def on_show(self):
        data = self.controller.get_last_score()
        if data:
            self.summary_var.config(text=f"Last score: {data.get('score', 0)} / {data.get('total', 0)}")
        else:
            self.summary_var.config(text="No games played yet.")

    def set_summary(self, final: bool = False):
        data = self.controller.get_last_score()
        if data:
            msg = f"Final score: {data.get('score', 0)} / {data.get('total', 0)}" if final else f"Last score: {data.get('score', 0)} / {data.get('total', 0)}"
            self.summary_var.config(text=msg)

    def play_again(self):
        questions = self.controller.get_questions()
        game_frame = self.controller.frames["GameFrame"]
        game_frame.start_new_game(questions)
        self.controller.show_frame("GameFrame")
