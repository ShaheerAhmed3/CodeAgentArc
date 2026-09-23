from tkinter import ttk


class HelpFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self['padding'] = (20, 20)

        ttk.Label(self, text="Help & Instructions", style='Header.TLabel').pack(pady=(10, 10))
        text = (
            "Goal: Answer fraction questions correctly.\n\n"
            "Controls:\n"
            "- 1–4: Select an answer option\n"
            "- Enter: Submit\n"
            "- P: Pause/Resume\n"
            "- Esc: Return to main menu\n\n"
            "Scoring: +1 point per correct answer.\n\n"
            "Admin: Use Main Menu → Login, choose admin and enter password 'admin' (demo) to edit questions."
        )
        ttk.Label(self, text=text, wraplength=720, justify='left').pack(pady=(0, 10))

        ttk.Button(self, text="Back to Menu", command=lambda: controller.show_frame("MainMenuFrame")).pack(pady=10)
