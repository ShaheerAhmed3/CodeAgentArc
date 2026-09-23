import tkinter as tk
from tkinter import ttk, messagebox

from ..core.question import Question


class AdminFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self['padding'] = (10, 10)

        ttk.Label(self, text="Admin — Update Questions", style='Header.TLabel').grid(row=0, column=0, columnspan=3, pady=(10, 10))

        self.tree = ttk.Treeview(self, columns=("id", "prompt", "answer"), show='headings', height=10)
        self.tree.heading("id", text="ID")
        self.tree.heading("prompt", text="Prompt")
        self.tree.heading("answer", text="Answer")
        self.tree.column("id", width=80)
        self.tree.column("prompt", width=480)
        self.tree.column("answer", width=120)
        self.tree.grid(row=1, column=0, columnspan=3, sticky='nsew', padx=10, pady=10)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(1, weight=1)

        btns = ttk.Frame(self)
        btns.grid(row=2, column=0, columnspan=3, pady=6)
        ttk.Button(btns, text="Add", command=self.add).grid(row=0, column=0, padx=5)
        ttk.Button(btns, text="Edit", command=self.edit).grid(row=0, column=1, padx=5)
        ttk.Button(btns, text="Delete", command=self.delete).grid(row=0, column=2, padx=5)
        ttk.Button(btns, text="Save", command=self.save).grid(row=0, column=3, padx=5)
        ttk.Button(btns, text="Back to Menu", command=lambda: controller.show_frame("MainMenuFrame")).grid(row=0, column=4, padx=5)

        self.details = ttk.Frame(self)
        self.details.grid(row=3, column=0, columnspan=3, sticky='ew', padx=10, pady=10)
        self._add_labeled(self.details, 0, "ID:")
        self._add_labeled(self.details, 1, "Prompt:")
        self._add_labeled(self.details, 2, "Option 1:")
        self._add_labeled(self.details, 3, "Option 2:")
        self._add_labeled(self.details, 4, "Option 3:")
        self._add_labeled(self.details, 5, "Option 4:")
        self._add_labeled(self.details, 6, "Answer (must match one option):")

        self.inputs = [child for child in self.details.winfo_children() if isinstance(child, ttk.Entry)]

        self.tree.bind('<<TreeviewSelect>>', lambda e: self.populate_from_selection())

    def on_show(self):
        self.reload()

    def _add_labeled(self, parent, row, text):
        ttk.Label(parent, text=text).grid(row=row, column=0, sticky='e', padx=5, pady=2)
        entry = ttk.Entry(parent, width=80)
        entry.grid(row=row, column=1, sticky='ew', padx=5, pady=2)
        parent.columnconfigure(1, weight=1)

    def reload(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for q in self.controller.get_questions():
            self.tree.insert('', 'end', values=(q.id, q.prompt, q.answer))
        for inp in self.inputs:
            inp.delete(0, tk.END)

    def populate_from_selection(self):
        sel = self.tree.selection()
        if not sel:
            return
        item = self.tree.item(sel[0])
        qid, prompt, answer = item['values']
        # Need to load full question to get options
        full = None
        for q in self.controller.get_questions():
            if q.id == qid:
                full = q
                break
        if not full:
            return
        values = [qid, prompt] + full.options + [answer]
        for entry, val in zip(self.inputs, values):
            entry.delete(0, tk.END)
            entry.insert(0, str(val))

    def read_inputs(self):
        vals = [e.get().strip() for e in self.inputs]
        if len(vals) < 7:
            raise ValueError("All fields are required")
        qid, prompt, o1, o2, o3, o4, ans = vals
        options = [o1, o2, o3, o4]
        if ans not in options:
            raise ValueError("Answer must match one of the options")
        return Question(id=qid, prompt=prompt, options=options, answer=ans)

    def add(self):
        try:
            q = self.read_inputs()
            # Check duplicate id
            for existing in self.controller.get_questions():
                if existing.id == q.id:
                    messagebox.showerror("Duplicate ID", "A question with this ID already exists.")
                    return
            data = self.controller.get_questions()
            data.append(q)
            self.controller.save_questions(data)
            self.reload()
            messagebox.showinfo("Added", "Question added.")
        except Exception as ex:
            messagebox.showerror("Error", str(ex))

    def edit(self):
        try:
            q = self.read_inputs()
            data = self.controller.get_questions()
            found = False
            for i, existing in enumerate(data):
                if existing.id == q.id:
                    data[i] = q
                    found = True
                    break
            if not found:
                messagebox.showwarning("Not found", "Select an existing question to edit or use Add.")
                return
            self.controller.save_questions(data)
            self.reload()
            messagebox.showinfo("Saved", "Question updated.")
        except Exception as ex:
            messagebox.showerror("Error", str(ex))

    def delete(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a question to delete.")
            return
        item = self.tree.item(sel[0])
        qid = item['values'][0]
        if not messagebox.askyesno("Confirm", f"Delete question {qid}?"):
            return
        data = self.controller.get_questions()
        data = [q for q in data if q.id != qid]
        self.controller.save_questions(data)
        self.reload()

    def save(self):
        # No-op as changes are saved immediately, but keep for UX
        messagebox.showinfo("Saved", "All changes have been saved.")
