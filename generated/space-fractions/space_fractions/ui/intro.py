import tkinter as tk
from tkinter import ttk


class IntroFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self['padding'] = (20, 20)

        self.title = ttk.Label(self, text="Space Fractions", style='Header.TLabel')
        self.subtitle = ttk.Label(self, text="An interstellar journey to master fractions!")
        self.title.pack(pady=(80, 10))
        self.subtitle.pack(pady=(0, 40))

        self.canvas = tk.Canvas(self, width=600, height=200, bg="#0b0f1a", highlightthickness=0)
        self.canvas.pack()
        self.star_items = []
        for i in range(40):
            x, y = (i * 15) % 600, (i * 37) % 200
            item = self.canvas.create_oval(x, y, x+2, y+2, fill="#e6edf3", outline="")
            self.star_items.append(item)

        btn = ttk.Button(self, text="Start", command=lambda: controller.show_frame("MainMenuFrame"))
        btn.pack(pady=30)
        btn.focus_set()

        self._animating = False

    def on_show(self):
        if not self._animating:
            self._animating = True
            self.animate()

    def animate(self):
        # simple starfield drift animation
        for item in self.star_items:
            self.canvas.move(item, -1, 0)
            x1, y1, x2, y2 = self.canvas.coords(item)
            if x2 < 0:
                # wrap around
                dx = 600 - x1
                self.canvas.move(item, dx, 0)
        if self._animating:
            self.after(50, self.animate)
