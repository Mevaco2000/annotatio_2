from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


class BaseDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.result = None
        self.columnconfigure(0, weight=1)

    def show(self):
        self.wait_window(self)
        return self.result


class LabelDialog(BaseDialog):
    LABEL_TYPES = [
        "Bounding box",
        "Segmentacja (maska)",
        "Skeleton",
        "Polygon",
        "Point",
        "Polyline",
        "Klasyfikacja",
    ]

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, "Dodaj etykiete")
        self.preview_path = tk.StringVar()
        self.name_var = tk.StringVar()
        self.type_var = tk.StringVar(value=self.LABEL_TYPES[0])

        body = ttk.Frame(self, padding=16)
        body.grid(sticky="nsew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Nazwa etykiety").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(body, textvariable=self.name_var, width=32).grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(body, text="Typ etykiety").grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Combobox(body, textvariable=self.type_var, values=self.LABEL_TYPES, state="readonly").grid(
            row=1, column=1, sticky="ew", pady=(0, 8)
        )

        ttk.Label(body, text="Zdjecie podgladowe").grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(body, textvariable=self.preview_path, width=32).grid(row=2, column=1, sticky="ew", pady=(0, 8))
        ttk.Button(body, text="Wybierz", command=self._pick_preview).grid(row=2, column=2, padx=(8, 0), pady=(0, 8))

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=3, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Anuluj", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Zapisz", command=self._save).pack(side="right")

    def _pick_preview(self) -> None:
        file_path = filedialog.askopenfilename(
            parent=self,
            title="Wybierz zdjecie podgladowe",
            filetypes=[("Obrazy", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("Wszystkie", "*.*")],
        )
        if file_path:
            self.preview_path.set(file_path)

    def _save(self) -> None:
        if not self.name_var.get().strip():
            messagebox.showerror("Etykieta", "Podaj nazwe etykiety.", parent=self)
            return
        self.result = {
            "name": self.name_var.get().strip(),
            "label_type": self.type_var.get(),
            "preview_image_path": self.preview_path.get().strip() or None,
        }
        self.destroy()


class CreateProjectDialog(BaseDialog):
    PROJECT_TYPES = ["Klasyfikacja", "Wykrywanie"]

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, "Create New Project")
        self.name_var = tk.StringVar()
        self.project_type_var = tk.StringVar(value=self.PROJECT_TYPES[0])
        self.labels: list[dict[str, str | None]] = []

        body = ttk.Frame(self, padding=16)
        body.grid(sticky="nsew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Nazwa projektu").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(body, textvariable=self.name_var, width=36).grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(body, text="Typ projektu").grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Combobox(body, textvariable=self.project_type_var, values=self.PROJECT_TYPES, state="readonly").grid(
            row=1, column=1, sticky="ew", pady=(0, 8)
        )

        ttk.Label(body, text="Etykiety projektu").grid(row=2, column=0, sticky="nw", pady=(0, 8))
        list_frame = ttk.Frame(body)
        list_frame.grid(row=2, column=1, sticky="ew", pady=(0, 8))
        list_frame.columnconfigure(0, weight=1)
        self.labels_list = tk.Listbox(list_frame, height=6)
        self.labels_list.grid(row=0, column=0, sticky="ew")
        ttk.Button(list_frame, text="Dodaj etykiete", command=self._add_label).grid(row=1, column=0, sticky="e", pady=(8, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Anuluj", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Utworz projekt", command=self._save).pack(side="right")

    def _add_label(self) -> None:
        dialog = LabelDialog(self)
        payload = dialog.show()
        if not payload:
            return
        self.labels.append(payload)
        self.labels_list.insert(tk.END, f"{payload['name']} [{payload['label_type']}]")

    def _save(self) -> None:
        if not self.name_var.get().strip():
            messagebox.showerror("Projekt", "Podaj nazwe projektu.", parent=self)
            return
        if not self.labels:
            messagebox.showerror("Projekt", "Dodaj przynajmniej jedna etykiete.", parent=self)
            return
        self.result = {
            "name": self.name_var.get().strip(),
            "project_type": self.project_type_var.get(),
            "labels": self.labels,
        }
        self.destroy()


class ExportDialog(BaseDialog):
    EXPORT_FORMATS = ["JSON (native)", "CSV", "TXT summary"]

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, "Export Dataset")
        self.format_var = tk.StringVar(value=self.EXPORT_FORMATS[0])
        self.destination_var = tk.StringVar()
        self.include_images_var = tk.BooleanVar(value=True)
        self.train_var = tk.IntVar(value=70)
        self.valid_var = tk.IntVar(value=20)
        self.test_var = tk.IntVar(value=10)

        body = ttk.Frame(self, padding=16)
        body.grid(sticky="nsew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Format eksportu").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Combobox(body, textvariable=self.format_var, values=self.EXPORT_FORMATS, state="readonly").grid(
            row=0, column=1, sticky="ew", pady=(0, 8)
        )

        ttk.Label(body, text="Split train").grid(row=1, column=0, sticky="w")
        ttk.Scale(body, from_=0, to=100, variable=self.train_var, command=self._sync_split).grid(
            row=1, column=1, sticky="ew"
        )
        ttk.Label(body, textvariable=self.train_var).grid(row=1, column=2, padx=(8, 0))

        ttk.Label(body, text="Split valid").grid(row=2, column=0, sticky="w")
        ttk.Scale(body, from_=0, to=100, variable=self.valid_var, command=self._sync_split).grid(
            row=2, column=1, sticky="ew"
        )
        ttk.Label(body, textvariable=self.valid_var).grid(row=2, column=2, padx=(8, 0))

        ttk.Label(body, text="Split test").grid(row=3, column=0, sticky="w")
        ttk.Scale(body, from_=0, to=100, variable=self.test_var, command=self._sync_split).grid(
            row=3, column=1, sticky="ew"
        )
        ttk.Label(body, textvariable=self.test_var).grid(row=3, column=2, padx=(8, 0))

        ttk.Checkbutton(body, text="Kopiuj obrazy razem z etykietami", variable=self.include_images_var).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(8, 8)
        )

        ttk.Label(body, text="Folder docelowy").grid(row=5, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(body, textvariable=self.destination_var, width=36).grid(row=5, column=1, sticky="ew", pady=(0, 8))
        ttk.Button(body, text="Wybierz folder", command=self._pick_directory).grid(row=5, column=2, padx=(8, 0), pady=(0, 8))

        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, columnspan=3, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Anuluj", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Export", command=self._save).pack(side="right")

    def _sync_split(self, _value: str) -> None:
        total = self.train_var.get() + self.valid_var.get() + self.test_var.get()
        if total == 100:
            return
        if total == 0:
            self.train_var.set(100)
            self.valid_var.set(0)
            self.test_var.set(0)
            return
        scale = 100 / total
        train = int(round(self.train_var.get() * scale))
        valid = int(round(self.valid_var.get() * scale))
        test = max(0, 100 - train - valid)
        self.train_var.set(train)
        self.valid_var.set(valid)
        self.test_var.set(test)

    def _pick_directory(self) -> None:
        folder = filedialog.askdirectory(parent=self, title="Wybierz folder eksportu")
        if folder:
            self.destination_var.set(folder)

    def _save(self) -> None:
        if not self.destination_var.get().strip():
            messagebox.showerror("Eksport", "Wybierz folder docelowy.", parent=self)
            return
        self.result = {
            "export_format": self.format_var.get(),
            "split": {
                "train": self.train_var.get(),
                "valid": self.valid_var.get(),
                "test": self.test_var.get(),
            },
            "include_images": self.include_images_var.get(),
            "destination_folder": self.destination_var.get().strip(),
        }
        self.destroy()


class CreateTaskDialog(BaseDialog):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, "Create New Task")
        self.name_var = tk.StringVar()
        self.folder_var = tk.StringVar()

        body = ttk.Frame(self, padding=16)
        body.grid(sticky="nsew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Nazwa taska").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(body, textvariable=self.name_var, width=36).grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(body, text="Folder z datasetem").grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(body, textvariable=self.folder_var, width=36).grid(row=1, column=1, sticky="ew", pady=(0, 8))
        ttk.Button(body, text="Wybierz", command=self._pick_directory).grid(row=1, column=2, padx=(8, 0), pady=(0, 8))

        buttons = ttk.Frame(body)
        buttons.grid(row=2, column=0, columnspan=3, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Anuluj", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Utworz task", command=self._save).pack(side="right")

    def _pick_directory(self) -> None:
        folder = filedialog.askdirectory(parent=self, title="Wybierz folder z obrazami")
        if folder:
            self.folder_var.set(folder)
            if not self.name_var.get().strip():
                self.name_var.set(Path(folder).name)

    def _save(self) -> None:
        if not self.name_var.get().strip():
            messagebox.showerror("Task", "Podaj nazwe taska.", parent=self)
            return
        self.result = {
            "task_name": self.name_var.get().strip(),
            "dataset_folder": self.folder_var.get().strip(),
        }
        self.destroy()


class MergeDialog(BaseDialog):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        source_label: str,
        target_label: str,
        options: list[tuple[int, str]],
    ) -> None:
        super().__init__(parent, title)
        self.options = options
        self.source_var = tk.StringVar(value=options[0][1])
        self.target_var = tk.StringVar(value=options[-1][1])

        body = ttk.Frame(self, padding=16)
        body.grid(sticky="nsew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text=source_label).grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Combobox(body, textvariable=self.source_var, values=[item[1] for item in options], state="readonly").grid(
            row=0, column=1, sticky="ew", pady=(0, 8)
        )

        ttk.Label(body, text=target_label).grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Combobox(body, textvariable=self.target_var, values=[item[1] for item in options], state="readonly").grid(
            row=1, column=1, sticky="ew", pady=(0, 8)
        )

        buttons = ttk.Frame(body)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Anuluj", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Scal", command=self._save).pack(side="right")

    def _save(self) -> None:
        self.result = {
            "source_id": self._resolve_id(self.source_var.get()),
            "target_id": self._resolve_id(self.target_var.get()),
        }
        self.destroy()

    def _resolve_id(self, label: str) -> int:
        for item_id, item_label in self.options:
            if item_label == label:
                return item_id
        raise ValueError("Nie znaleziono wybranego elementu.")


class CreateLabelDialog(BaseDialog):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, "Dodaj etykietę")
        self.name_var = tk.StringVar()
        self.label_type_var = tk.StringVar(value=AppService.LABEL_TYPES[0])
        self.preview_path_var = tk.StringVar()
        self._build()

    def _build(self) -> None:
        container = ttk.Frame(self, padding=16)
        container.grid(sticky="nsew")

        ttk.Label(container, text="Nazwa etykiety").grid(row=0, column=0, sticky="w")
        ttk.Entry(container, textvariable=self.name_var, width=40).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        ttk.Label(container, text="Typ etykiety").grid(row=2, column=0, sticky="w")
        ttk.Combobox(
            container,
            textvariable=self.label_type_var,
            values=AppService.LABEL_TYPES,
            state="readonly",
            width=36,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        ttk.Label(container, text="Zdjęcie podglądowe (opcjonalnie)").grid(row=4, column=0, sticky="w")
        ttk.Entry(container, textvariable=self.preview_path_var, width=40).grid(row=5, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(container, text="Wybierz zdjęcie", command=self._browse_preview).grid(row=5, column=1, sticky="ew", padx=(8, 0))

        actions = ttk.Frame(container)
        actions.grid(row=6, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(actions, text="Anuluj", command=self._close).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Zapisz", command=self._save).grid(row=0, column=1)

    def _browse_preview(self) -> None:
        file_path = filedialog.askopenfilename(
            parent=self,
            title="Wybierz zdjęcie podglądowe",
            filetypes=[("Obrazy", "*.png *.jpg *.jpeg *.bmp *.gif *.webp")],
        )
        if file_path:
            self.preview_path_var.set(file_path)

    def _save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Brak danych", "Podaj nazwę etykiety.", parent=self)
            return
        preview_path = self.preview_path_var.get().strip() or None
        if preview_path and not Path(preview_path).exists():
            messagebox.showwarning("Nieprawidłowa ścieżka", "Wybrane zdjęcie podglądowe nie istnieje.", parent=self)
            return
        self.result = {
            "name": name,
            "label_type": self.label_type_var.get(),
            "preview_image_path": preview_path,
        }
        self.destroy()


class CreateProjectDialog(BaseDialog):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, "Create New Project")
        self.name_var = tk.StringVar()
        self.project_type_var = tk.StringVar(value=AppService.PROJECT_TYPES[0])
        self.labels: list[dict[str, str | None]] = []
        self._build()

    def _build(self) -> None:
        container = ttk.Frame(self, padding=18)
        container.grid(sticky="nsew")

        ttk.Label(container, text="Nazwa projektu").grid(row=0, column=0, sticky="w")
        ttk.Entry(container, textvariable=self.name_var, width=44).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        ttk.Label(container, text="Typ projektu").grid(row=2, column=0, sticky="w")
        ttk.Combobox(
            container,
            textvariable=self.project_type_var,
            values=AppService.PROJECT_TYPES,
            state="readonly",
            width=40,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        ttk.Label(container, text="Etykiety startowe").grid(row=4, column=0, sticky="w")
        self.labels_list = tk.Listbox(container, height=6, width=48)
        self.labels_list.grid(row=5, column=0, sticky="ew")
        ttk.Button(container, text="Dodaj etykietę", command=self._add_label).grid(row=5, column=1, sticky="nsew", padx=(8, 0))

        actions = ttk.Frame(container)
        actions.grid(row=6, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(actions, text="Anuluj", command=self._close).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Utwórz projekt", command=self._save).grid(row=0, column=1)

    def _add_label(self) -> None:
        dialog = CreateLabelDialog(self)
        result = dialog.show()
        if not result:
            return
        self.labels.append(result)
        self.labels_list.insert(tk.END, f"{result['name']} [{result['label_type']}]")

    def _save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Brak danych", "Podaj nazwę projektu.", parent=self)
            return
        self.result = {
            "name": name,
            "project_type": self.project_type_var.get(),
            "labels": self.labels,
        }
        self.destroy()


class ExportDatasetDialog(BaseDialog):
    def __init__(self, parent: tk.Misc, project_name: str) -> None:
        super().__init__(parent, f"Export Dataset: {project_name}")
        self.format_var = tk.StringVar(value=AppService.EXPORT_FORMATS[0])
        self.train_var = tk.IntVar(value=70)
        self.valid_var = tk.IntVar(value=20)
        self.test_var = tk.IntVar(value=10)
        self.include_images_var = tk.BooleanVar(value=True)
        self.folder_var = tk.StringVar()
        self._build()
        self._update_test_value()

    def _build(self) -> None:
        container = ttk.Frame(self, padding=18)
        container.grid(sticky="nsew")

        ttk.Label(container, text="Format eksportu").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            container,
            textvariable=self.format_var,
            values=AppService.EXPORT_FORMATS,
            state="readonly",
            width=34,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        ttk.Label(container, text="Split train").grid(row=2, column=0, sticky="w")
        tk.Scale(container, from_=0, to=100, orient="horizontal", variable=self.train_var, command=lambda _value: self._update_test_value()).grid(
            row=3, column=0, columnspan=2, sticky="ew"
        )
        ttk.Label(container, text="Split valid").grid(row=4, column=0, sticky="w", pady=(12, 0))
        tk.Scale(container, from_=0, to=100, orient="horizontal", variable=self.valid_var, command=lambda _value: self._update_test_value()).grid(
            row=5, column=0, columnspan=2, sticky="ew"
        )
        self.test_label = ttk.Label(container, text="Split test: 10%")
        self.test_label.grid(row=6, column=0, sticky="w", pady=(8, 12))

        ttk.Checkbutton(
            container,
            text="Zapisuj obrazy razem z etykietami",
            variable=self.include_images_var,
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(0, 12))

        ttk.Label(container, text="Folder docelowy").grid(row=8, column=0, sticky="w")
        ttk.Entry(container, textvariable=self.folder_var, width=36).grid(row=9, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(container, text="Wybierz folder", command=self._browse_folder).grid(row=9, column=1, sticky="ew", padx=(8, 0))

        actions = ttk.Frame(container)
        actions.grid(row=10, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(actions, text="Anuluj", command=self._close).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Export", command=self._save).grid(row=0, column=1)

    def _update_test_value(self) -> None:
        train_value = self.train_var.get()
        valid_value = self.valid_var.get()
        if train_value + valid_value > 100:
            self.valid_var.set(max(0, 100 - train_value))
            valid_value = self.valid_var.get()
        self.test_var.set(100 - train_value - valid_value)
        self.test_label.configure(text=f"Split test: {self.test_var.get()}%")

    def _browse_folder(self) -> None:
        directory = filedialog.askdirectory(parent=self, title="Wybierz folder eksportu")
        if directory:
            self.folder_var.set(directory)

    def _save(self) -> None:
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("Brak danych", "Wybierz folder eksportu.", parent=self)
            return
        self.result = {
            "format": self.format_var.get(),
            "split_train": self.train_var.get(),
            "split_valid": self.valid_var.get(),
            "split_test": self.test_var.get(),
            "include_images": self.include_images_var.get(),
            "folder": folder,
        }
        self.destroy()


class CreateTaskDialog(BaseDialog):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, "Create New Task")
        self.name_var = tk.StringVar()
        self.folder_var = tk.StringVar()
        self._build()

    def _build(self) -> None:
        container = ttk.Frame(self, padding=18)
        container.grid(sticky="nsew")

        ttk.Label(container, text="Nazwa taska").grid(row=0, column=0, sticky="w")
        ttk.Entry(container, textvariable=self.name_var, width=40).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        ttk.Label(container, text="Folder z datasetem").grid(row=2, column=0, sticky="w")
        ttk.Entry(container, textvariable=self.folder_var, width=40).grid(row=3, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(container, text="Wybierz folder", command=self._browse_folder).grid(row=3, column=1, sticky="ew", padx=(8, 0))

        actions = ttk.Frame(container)
        actions.grid(row=4, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(actions, text="Anuluj", command=self._close).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Utwórz task", command=self._save).grid(row=0, column=1)

    def _browse_folder(self) -> None:
        directory = filedialog.askdirectory(parent=self, title="Wybierz folder datasetu")
        if directory:
            self.folder_var.set(directory)
            if not self.name_var.get().strip():
                self.name_var.set(Path(directory).name)

    def _save(self) -> None:
        if not self.name_var.get().strip():
            messagebox.showwarning("Brak danych", "Podaj nazwę taska.", parent=self)
            return
        self.result = {
            "name": self.name_var.get().strip(),
            "folder": self.folder_var.get().strip(),
        }
        self.destroy()


class MergeSelectionDialog(BaseDialog):
    def __init__(self, parent: tk.Misc, title: str, items: list[tuple[int, str]]) -> None:
        super().__init__(parent, title)
        self.items = items
        self.source_var = tk.StringVar(value=items[0][1] if items else "")
        self.target_var = tk.StringVar(value=items[1][1] if len(items) > 1 else (items[0][1] if items else ""))
        self._build()

    def _build(self) -> None:
        container = ttk.Frame(self, padding=18)
        container.grid(sticky="nsew")
        labels = [label for _, label in self.items]

        ttk.Label(container, text="Źródło").grid(row=0, column=0, sticky="w")
        ttk.Combobox(container, textvariable=self.source_var, values=labels, state="readonly", width=38).grid(
            row=1, column=0, sticky="ew", pady=(4, 12)
        )
        ttk.Label(container, text="Cel").grid(row=2, column=0, sticky="w")
        ttk.Combobox(container, textvariable=self.target_var, values=labels, state="readonly", width=38).grid(
            row=3, column=0, sticky="ew"
        )

        actions = ttk.Frame(container)
        actions.grid(row=4, column=0, sticky="e", pady=(16, 0))
        ttk.Button(actions, text="Anuluj", command=self._close).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Scal", command=self._save).grid(row=0, column=1)

    def _save(self) -> None:
        source_label = self.source_var.get()
        target_label = self.target_var.get()
        if not source_label or not target_label:
            messagebox.showwarning("Brak wyboru", "Wybierz element źródłowy i docelowy.", parent=self)
            return
        source_id = next(item_id for item_id, label in self.items if label == source_label)
        target_id = next(item_id for item_id, label in self.items if label == target_label)
        if source_id == target_id:
            messagebox.showwarning("Nieprawidłowy wybór", "Źródło i cel muszą być różne.", parent=self)
            return
        self.result = {"source_id": source_id, "target_id": target_id}
        self.destroy()