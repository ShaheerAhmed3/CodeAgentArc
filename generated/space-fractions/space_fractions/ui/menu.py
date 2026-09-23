import tkinter as tk
from tkinter import ttk, simpledialog, messagebox


class MainMenuFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self['padding'] = (20, 20)

        ttk.Label(self, text="Main Menu", style='Header.TLabel').pack(pady=(40, 20))

        self.start_btn = ttk.Button(self, text="Start Game", command=self.start_game)
        self.score_btn = ttk.Button(self, text="View Score", command=lambda: controller.show_frame("ScoreFrame"))
        self.help_btn = ttk.Button(self, text="View Help", command=lambda: controller.show_frame("HelpFrame"))
        self.admin_btn = ttk.Button(self, text="Update Questions (Admin)", command=self.admin)
        self.login_btn = ttk.Button(self, text="Login", command=self.login)
        self.logout_btn = ttk.Button(self, text="Logout", command=controller.logout)
        self.exit_btn = ttk.Button(self, text="Exit", command=controller.destroy)

        for b in (self.start_btn, self.score_btn, self.help_btn, self.admin_btn, self.login_btn, self.logout_btn, self.exit_btn):
            b.pack(pady=6)

        self.status = ttk.Label(self, text="Not logged in")
        self.status.pack(pady=(16, 0))

        self.bind_all('<Control-q>', lambda e: controller.destroy())

    def on_show(self):
        user = self.controller.current_user
        if user:
            self.status.config(text=f"Logged in as: {user.username}{' (admin)' if user.is_admin else ''}")
        else:
            self.status.config(text="Not logged in")

    def start_game(self):
        # Initialize GameFrame with fresh questions
        try:
            questions = self.controller.get_questions()
            game_frame = self.controller.frames["GameFrame"]
            game_frame.start_new_game(questions)
            self.controller.show_frame("GameFrame")
        except Exception as ex:
            messagebox.showerror("Error", f"Could not start game: {ex}")

    def admin(self):
        user = self.controller.current_user
        if not user or not user.is_admin:
            messagebox.showwarning("Restricted", "Admin access required. Please login as admin.")
            return
        self.controller.show_frame("AdminFrame")

    def login(self):
        username = simpledialog.askstring("Login", "Enter username:", parent=self)
        if username is None or username.strip() == "":
            return
        # Simple local admin gate
        is_admin = False
        if messagebox.askyesno("Admin?", "Login as admin? This requires a password."):
            pwd = simpledialog.askstring("Admin Password", "Enter admin password:", show='*', parent=self)
            if pwd == 'admin':
                is_admin = True
            else:
                messagebox.showerror("Login failed", "Incorrect admin password. Logging in as regular user.")
        self.controller.set_user(username=username.strip(), is_admin=is_admin)
