import json
import os
import tkinter as tk
from tkinter import ttk, messagebox

from .core.user import User
from .services.user_service import UserService
from .services.question_service import QuestionService
from .ui.intro import IntroFrame
from .ui.menu import MainMenuFrame
from .ui.game_view import GameFrame
from .ui.help_view import HelpFrame
from .ui.score_view import ScoreFrame
from .ui.admin_view import AdminFrame


class SpaceFractionsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Space Fractions")
        self.geometry("800x600")
        self.minsize(760, 520)
        self.configure(bg="#0b0f1a")

        style = ttk.Style()
        # Use default theme for portability; customize colors
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure('TFrame', background="#0b0f1a")
        style.configure('TLabel', background="#0b0f1a", foreground="#e6edf3", font=("Helvetica", 12))
        style.configure('Header.TLabel', font=("Helvetica", 18, "bold"))
        style.configure('TButton', font=("Helvetica", 12))

        self.user_service = UserService()
        self.question_service = QuestionService()

        # Container that stacks all frames on top of each other using a single grid cell
        self.container = ttk.Frame(self)
        self.container.pack(fill=tk.BOTH, expand=True)
        # Ensure the single grid cell expands to fill the container on all platforms
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for F in (IntroFrame, MainMenuFrame, GameFrame, HelpFrame, ScoreFrame, AdminFrame):
            frame = F(parent=self.container, controller=self)
            self.frames[F.__name__] = frame
            # All frames occupy the same grid cell and are raised as needed
            frame.grid(row=0, column=0, sticky="nsew")

        # Defer the initial raise until idle so geometry/layout is ready (avoids blank on macOS)
        self.after_idle(lambda: self.show_frame("IntroFrame"))

        # Keyboard global shortcuts
        self.bind("<Escape>", lambda e: self.show_frame("MainMenuFrame"))

    def show_frame(self, name: str):
        frame = self.frames[name]
        if hasattr(frame, 'on_show'):
            try:
                frame.on_show()
            except Exception as ex:
                messagebox.showerror("Error", f"Error preparing screen: {ex}")
        frame.tkraise()

    # Session helpers
    @property
    def current_user(self) -> User:
        return self.user_service.current_user

    def set_user(self, username: str, is_admin: bool = False):
        self.user_service.login(username=username, is_admin=is_admin)
        messagebox.showinfo("Login", f"Logged in as {username}{' (admin)' if is_admin else ''}")
        self.show_frame("MainMenuFrame")

    def logout(self):
        self.user_service.logout()
        messagebox.showinfo("Logout", "You have been logged out.")
        self.show_frame("MainMenuFrame")

    def get_questions(self):
        return self.question_service.load_questions()

    def save_questions(self, questions):
        self.question_service.save_questions(questions)

    def get_last_score(self):
        return self.user_service.load_last_score()

    def save_last_score(self, score_dict):
        self.user_service.save_last_score(score_dict)
