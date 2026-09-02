from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from model.services import AppService

try:
    from PIL import Image, ImageOps, ImageTk
except ImportError:
    Image = None
    ImageOps = None
    ImageTk = None


def center_window_on_screen(window: tk.Toplevel) -> None:
    try:
        window.update_idletasks()
        width = max(window.winfo_reqwidth(), window.winfo_width(), 320)
        height = max(window.winfo_reqheight(), window.winfo_height(), 180)
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        pos_x = max(0, (screen_width - width) // 2)
        pos_y = max(0, (screen_height - height) // 2)
        window.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
    except tk.TclError:
        return


class BaseDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.result = None
        self.columnconfigure(0, weight=1)
        self.after_idle(lambda: center_window_on_screen(self))

    def show(self):
        self.wait_window(self)
        return self.result

    def _close(self) -> None:
        self.destroy()


class HoverToolTip:
    def __init__(self, widget: tk.Widget, text_provider) -> None:
        self.widget = widget
        self.text_provider = text_provider
        self.tip_window: tk.Toplevel | None = None
        self.widget.bind("<Enter>", self._show, add="+")
        self.widget.bind("<Leave>", self._hide, add="+")
        self.widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        text = self.text_provider() if callable(self.text_provider) else str(self.text_provider)
        if not text:
            return
        self._hide()
        x_pos = self.widget.winfo_rootx() + 18
        y_pos = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x_pos}+{y_pos}")
        tk.Label(
            self.tip_window,
            text=text,
            justify="left",
            wraplength=460,
            background="#fff7ed",
            borderwidth=1,
            relief="solid",
            padx=8,
            pady=6,
        ).pack()

    def _hide(self, _event=None) -> None:
        if self.tip_window is not None:
            self.tip_window.destroy()
            self.tip_window = None


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
    def __init__(self, parent: tk.Misc, export_formats: list[str] | None = None) -> None:
        super().__init__(parent, "Export Dataset")
        self.export_formats = list(export_formats or AppService.EXPORT_FORMATS)
        self.format_var = tk.StringVar(value=self.export_formats[0])
        self.destination_var = tk.StringVar()
        self.include_images_var = tk.BooleanVar(value=True)
        self.train_var = tk.IntVar(value=70)
        self.valid_var = tk.IntVar(value=20)
        self.test_var = tk.IntVar(value=10)
        self._tooltips: list[HoverToolTip] = []

        body = ttk.Frame(self, padding=16)
        body.grid(sticky="nsew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Format eksportu").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.format_combo = ttk.Combobox(body, textvariable=self.format_var, values=self.export_formats, state="readonly")
        self.format_combo.grid(row=0, column=1, sticky="ew", pady=(0, 8))
        info_label = tk.Label(body, text="(i)", fg="#2563eb", cursor="question_arrow")
        info_label.grid(row=0, column=2, sticky="w", padx=(8, 0), pady=(0, 8))

        self._tooltips.append(HoverToolTip(self.format_combo, self._get_selected_format_help))
        self._tooltips.append(HoverToolTip(info_label, self._get_selected_format_help))

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

    def _get_selected_format_help(self) -> str:
        details = AppService.get_export_format_details(self.format_var.get())
        image_note = "Kopiowanie obrazów: wlaczone." if self.include_images_var.get() else "Kopiowanie obrazów: wylaczone."
        return f"{details['summary']}\n\nStruktura po eksporcie:\n{details['structure']}\n\n{image_note}"

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


class ImportDatasetDialog(BaseDialog):
    def __init__(self, parent: tk.Misc, import_formats: list[str] | None = None) -> None:
        super().__init__(parent, "Import Dataset")
        self.import_formats = list(import_formats or AppService.DATASET_IMPORT_FORMATS)
        default_format = self.import_formats[0] if self.import_formats else ""
        self.task_name_var = tk.StringVar()
        self.dataset_folder_var = tk.StringVar()
        self.format_var = tk.StringVar(value=default_format)
        self._build()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=16)
        body.grid(sticky="nsew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Nazwa taska (opcjonalnie)").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(body, textvariable=self.task_name_var, width=36).grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(body, text="Folder datasetu").grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(body, textvariable=self.dataset_folder_var, width=36).grid(row=1, column=1, sticky="ew", pady=(0, 8))
        ttk.Button(body, text="Wybierz folder", command=self._pick_directory).grid(row=1, column=2, padx=(8, 0), pady=(0, 8))

        ttk.Label(body, text="Format annotacji").grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Combobox(body, textvariable=self.format_var, values=self.import_formats, state="readonly").grid(
            row=2,
            column=1,
            sticky="ew",
            pady=(0, 8),
        )

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=3, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Anuluj", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Importuj", command=self._save).pack(side="right")

    def _pick_directory(self) -> None:
        folder = filedialog.askdirectory(parent=self, title="Wybierz folder datasetu")
        if folder:
            self.dataset_folder_var.set(folder)
            if not self.task_name_var.get().strip():
                self.task_name_var.set(Path(folder).name)

    def _save(self) -> None:
        task_name = self.task_name_var.get().strip()
        dataset_folder = self.dataset_folder_var.get().strip()
        dataset_format = self.format_var.get().strip()

        if not dataset_folder:
            messagebox.showerror("Import Dataset", "Wybierz folder datasetu.", parent=self)
            return
        if not dataset_format:
            messagebox.showerror("Import Dataset", "Wybierz format annotacji.", parent=self)
            return

        self.result = {
            "task_name": task_name,
            "dataset_folder": dataset_folder,
            "dataset_format": dataset_format,
        }
        self.destroy()


class ImportTypeFilterDialog(BaseDialog):
    def __init__(self, parent: tk.Misc, detected_types: list[str]) -> None:
        super().__init__(parent, "Filtr typow etykiet")
        unique_types: list[str] = []
        for label_type in detected_types:
            if label_type not in unique_types:
                unique_types.append(label_type)
        self.detected_types = unique_types
        self.type_vars: dict[str, tk.BooleanVar] = {
            label_type: tk.BooleanVar(value=True) for label_type in self.detected_types
        }
        self._build()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=16)
        body.grid(sticky="nsew")
        body.columnconfigure(0, weight=1)

        ttk.Label(body, text="Wykryto wiele typow etykiet. Wybierz, co importowac:").grid(
            row=0,
            column=0,
            sticky="w",
            pady=(0, 10),
        )

        checks = ttk.Frame(body)
        checks.grid(row=1, column=0, sticky="ew")
        checks.columnconfigure(0, weight=1)
        for index, label_type in enumerate(self.detected_types):
            ttk.Checkbutton(checks, text=label_type, variable=self.type_vars[label_type]).grid(
                row=index,
                column=0,
                sticky="w",
                pady=(0, 4),
            )

        buttons = ttk.Frame(body)
        buttons.grid(row=2, column=0, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Anuluj", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Importuj", command=self._save).pack(side="right")

    def _save(self) -> None:
        selected_types = [label_type for label_type, flag in self.type_vars.items() if flag.get()]
        if not selected_types:
            messagebox.showwarning("Import Dataset", "Wybierz przynajmniej jeden typ etykiety.", parent=self)
            return
        self.result = {"allowed_label_types": selected_types}
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


class MergeProjectsDialog(BaseDialog):
    def __init__(self, parent: tk.Misc, options: list[tuple[int, str]]) -> None:
        super().__init__(parent, "Scal projekty")
        self.options = options
        self.target_var = tk.StringVar(value=options[0][1] if options else "")
        self.delete_sources_var = tk.BooleanVar(value=False)
        self._build()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=16)
        body.grid(sticky="nsew")
        body.columnconfigure(0, weight=1)

        ttk.Label(body, text="Projekt docelowy").grid(row=0, column=0, sticky="w")
        self.target_combo = ttk.Combobox(
            body,
            textvariable=self.target_var,
            values=[label for _, label in self.options],
            state="readonly",
            width=42,
        )
        self.target_combo.grid(row=1, column=0, sticky="ew", pady=(4, 12))

        ttk.Label(body, text="Projekty zrodlowe do scalenia (mozesz wybrac wiele)").grid(row=2, column=0, sticky="w")
        list_wrap = ttk.Frame(body)
        list_wrap.grid(row=3, column=0, sticky="nsew", pady=(4, 0))
        list_wrap.columnconfigure(0, weight=1)
        list_wrap.rowconfigure(0, weight=1)

        self.sources_list = tk.Listbox(list_wrap, selectmode=tk.MULTIPLE, height=10, exportselection=False)
        self.sources_list.grid(row=0, column=0, sticky="nsew")
        for _, label in self.options:
            self.sources_list.insert(tk.END, label)

        scrollbar = ttk.Scrollbar(list_wrap, orient="vertical", command=self.sources_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.sources_list.configure(yscrollcommand=scrollbar.set)

        quick_actions = ttk.Frame(body)
        quick_actions.grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Button(quick_actions, text="Wybierz wszystkie", command=self._select_all_sources).pack(side="left")
        ttk.Button(quick_actions, text="Wyczysc wybor", command=self._clear_sources).pack(side="left", padx=(8, 0))

        ttk.Checkbutton(
            body,
            text="Usun projekty zrodlowe po udanym scaleniu",
            variable=self.delete_sources_var,
        ).grid(row=5, column=0, sticky="w", pady=(10, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Anuluj", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Scal", command=self._save).pack(side="right")

    def _select_all_sources(self) -> None:
        self.sources_list.selection_set(0, tk.END)

    def _clear_sources(self) -> None:
        self.sources_list.selection_clear(0, tk.END)

    def _save(self) -> None:
        target_label = self.target_var.get().strip()
        if not target_label:
            messagebox.showwarning("Scalanie projektow", "Wybierz projekt docelowy.", parent=self)
            return

        selected_indexes = list(self.sources_list.curselection())
        if not selected_indexes:
            messagebox.showwarning("Scalanie projektow", "Wybierz przynajmniej jeden projekt zrodlowy.", parent=self)
            return

        options_by_label = {label: item_id for item_id, label in self.options}
        target_id = options_by_label.get(target_label)
        if target_id is None:
            messagebox.showwarning("Scalanie projektow", "Nie znaleziono wybranego projektu docelowego.", parent=self)
            return

        source_ids: list[int] = []
        for index in selected_indexes:
            source_label = self.sources_list.get(index)
            source_id = options_by_label.get(source_label)
            if source_id is not None and source_id != target_id:
                source_ids.append(source_id)

        if not source_ids:
            messagebox.showwarning(
                "Scalanie projektow",
                "Lista projektow zrodlowych po odfiltrowaniu projektu docelowego jest pusta.",
                parent=self,
            )
            return

        self.result = {
            "target_id": target_id,
            "source_ids": source_ids,
            "delete_sources": bool(self.delete_sources_var.get()),
        }
        self.destroy()


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
    PREVIEW_CANVAS_SIZE = (520, 320)

    def __init__(self, parent: tk.Misc, default_storage_folder: str = "") -> None:
        super().__init__(parent, "Create New Project")
        self.resizable(True, True)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.name_var = tk.StringVar()
        self.project_type_var = tk.StringVar(value=AppService.PROJECT_TYPES[0])
        self.storage_folder_var = tk.StringVar(value=default_storage_folder)
        self.label_name_var = tk.StringVar()
        self.label_type_var = tk.StringVar(value=AppService.LABEL_TYPES[0])
        self.label_preview_var = tk.StringVar()
        self.skeleton_points_var = tk.IntVar(value=4)
        self.preview_status_var = tk.StringVar(value="Wybierz zdjęcie przykładowe, aby przygotować szkic etykiety.")
        self.labels: list[dict[str, str | None]] = []
        self._preview_points: list[dict[str, float]] = []
        self._preview_box: tuple[float, float, float, float] | None = None
        self._preview_dragging_bbox = False
        self._preview_photo = None
        self._scroll_canvas: tk.Canvas | None = None
        self._scroll_window_id: int | None = None
        self.label_type_combo: ttk.Combobox | None = None
        self.preview_source_label: ttk.Label | None = None
        self.preview_source_entry: ttk.Entry | None = None
        self.preview_source_button: ttk.Button | None = None
        self.preview_controls: ttk.Frame | None = None
        self.preview_status_label: ttk.Label | None = None
        self._classification_hidden_widgets: list[tk.Widget] = []
        self._build()
        self.project_type_var.trace_add("write", self._on_project_type_changed)
        self.label_type_var.trace_add("write", self._on_preview_type_changed)
        self.label_preview_var.trace_add("write", self._on_preview_source_changed)
        self.skeleton_points_var.trace_add("write", self._on_skeleton_points_changed)
        self._on_project_type_changed()
        self._update_preview_tools()
        self._refresh_preview_canvas()
        self._configure_scroll_geometry()

    def _build(self) -> None:
        outer = ttk.Frame(self)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        self._scroll_canvas = tk.Canvas(outer, highlightthickness=0)
        self._scroll_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=self._scroll_canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._scroll_canvas.configure(yscrollcommand=scrollbar.set)

        container = ttk.Frame(self._scroll_canvas, padding=18)
        self._scroll_window_id = self._scroll_canvas.create_window((0, 0), window=container, anchor="nw")
        container.bind("<Configure>", self._on_scroll_content_configure)
        self._scroll_canvas.bind("<Configure>", self._on_scroll_canvas_configure)
        self._scroll_canvas.bind("<Enter>", self._bind_scroll_events)
        self._scroll_canvas.bind("<Leave>", self._unbind_scroll_events)

        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)

        ttk.Label(container, text="Nazwa projektu").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Entry(container, textvariable=self.name_var, width=52).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        ttk.Label(container, text="Typ projektu").grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Combobox(
            container,
            textvariable=self.project_type_var,
            values=AppService.PROJECT_TYPES,
            state="readonly",
            width=48,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        ttk.Label(container, text="Folder zapisu projektu").grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Entry(container, textvariable=self.storage_folder_var, width=52).grid(row=5, column=0, sticky="ew", pady=(4, 12))
        ttk.Button(container, text="Wybierz folder", command=self._browse_storage_folder).grid(row=5, column=1, sticky="ew", padx=(8, 0), pady=(4, 12))

        ttk.Separator(container, orient="horizontal").grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        ttk.Label(container, text="Dodaj etykietę startową").grid(row=7, column=0, columnspan=2, sticky="w")

        ttk.Label(container, text="Nazwa etykiety").grid(row=8, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(container, textvariable=self.label_name_var, width=28).grid(row=9, column=0, sticky="ew", pady=(4, 12))

        ttk.Label(container, text="Typ etykiety").grid(row=8, column=1, sticky="w", pady=(8, 0))
        self.label_type_combo = ttk.Combobox(
            container,
            textvariable=self.label_type_var,
            values=AppService.LABEL_TYPES,
            state="readonly",
            width=26,
        )
        self.label_type_combo.grid(row=9, column=1, sticky="ew", pady=(4, 12), padx=(8, 0))

        self.preview_source_label = ttk.Label(container, text="Zdjęcie przykładowe dla etykiety")
        self.preview_source_label.grid(row=10, column=0, columnspan=2, sticky="w")
        self.preview_source_entry = ttk.Entry(container, textvariable=self.label_preview_var, width=52)
        self.preview_source_entry.grid(row=11, column=0, sticky="ew", pady=(4, 0))
        self.preview_source_button = ttk.Button(container, text="Wybierz zdjęcie", command=self._browse_label_preview)
        self.preview_source_button.grid(row=11, column=1, sticky="ew", padx=(8, 0), pady=(4, 0))

        self.preview_controls = ttk.Frame(container)
        self.preview_controls.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        ttk.Label(self.preview_controls, text="Interaktywny podgląd etykiety").pack(side="left")
        ttk.Label(self.preview_controls, text="Punkty skeletonu").pack(side="left", padx=(16, 4))
        self.skeleton_points_spinbox = ttk.Spinbox(
            self.preview_controls,
            from_=2,
            to=32,
            textvariable=self.skeleton_points_var,
            width=5,
        )
        self.skeleton_points_spinbox.pack(side="left")
        ttk.Button(self.preview_controls, text="Wyczyść szkic", command=self._clear_preview_definition).pack(side="right")
        ttk.Button(self.preview_controls, text="Cofnij", command=self._undo_preview_step).pack(side="right", padx=(0, 8))

        self.preview_canvas = tk.Canvas(
            container,
            width=self.PREVIEW_CANVAS_SIZE[0],
            height=self.PREVIEW_CANVAS_SIZE[1],
            background="#111827",
            highlightthickness=1,
            highlightbackground="#cbd5e1",
            cursor="crosshair",
        )
        self.preview_canvas.grid(row=13, column=0, columnspan=2, sticky="nsew")
        self.preview_canvas.bind("<ButtonPress-1>", self._on_preview_canvas_press)
        self.preview_canvas.bind("<B1-Motion>", self._on_preview_canvas_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self._on_preview_canvas_release)

        self.preview_status_label = ttk.Label(
            container,
            textvariable=self.preview_status_var,
            justify="left",
            wraplength=560,
        )
        self.preview_status_label.grid(row=14, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self._classification_hidden_widgets = [
            self.preview_source_label,
            self.preview_source_entry,
            self.preview_source_button,
            self.preview_controls,
            self.preview_canvas,
            self.preview_status_label,
        ]

        label_actions = ttk.Frame(container)
        label_actions.grid(row=15, column=0, columnspan=2, sticky="ew", pady=(12, 12))
        ttk.Button(label_actions, text="Dodaj etykietę", command=self._add_current_label).pack(side="left")
        ttk.Button(label_actions, text="Wyczyść pola", command=self._clear_label_form).pack(side="left", padx=(8, 0))
        ttk.Button(label_actions, text="Usuń zaznaczoną", command=self._remove_selected_label).pack(side="right")

        self.labels_tree = ttk.Treeview(container, columns=("type", "preview", "shape"), show="tree headings", height=7)
        self.labels_tree.grid(row=16, column=0, columnspan=2, sticky="nsew")
        self.labels_tree.heading("#0", text="Etykieta")
        self.labels_tree.heading("type", text="Typ")
        self.labels_tree.heading("preview", text="Zdjęcie przykładowe")
        self.labels_tree.heading("shape", text="Szkic")
        self.labels_tree.column("#0", width=180, anchor="w")
        self.labels_tree.column("type", width=160, anchor="center")
        self.labels_tree.column("preview", width=200, anchor="w")
        self.labels_tree.column("shape", width=120, anchor="center")

        actions = ttk.Frame(container)
        actions.grid(row=17, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(actions, text="Anuluj", command=self._close).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Utwórz projekt", command=self._save).grid(row=0, column=1)

    def _on_scroll_content_configure(self, _event: tk.Event) -> None:
        if self._scroll_canvas is not None:
            self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all"))

    def _is_classification_project(self) -> bool:
        return self.project_type_var.get() == "Klasyfikacja"

    def _get_available_label_types_for_project(self) -> list[str]:
        if self._is_classification_project():
            return ["Klasyfikacja"]
        return list(AppService.LABEL_TYPES)

    def _on_project_type_changed(self, *_args) -> None:
        available_label_types = self._get_available_label_types_for_project()
        if self.label_type_combo is not None:
            self.label_type_combo.configure(values=available_label_types)
        if self.label_type_var.get() not in available_label_types:
            self.label_type_var.set(available_label_types[0])

        if self._is_classification_project():
            self.label_preview_var.set("")
            self._preview_points = []

        self._update_preview_visibility()
        self._update_preview_status()
        self._refresh_preview_canvas()

    def _update_preview_visibility(self) -> None:
        if self._is_classification_project():
            for widget in self._classification_hidden_widgets:
                widget.grid_remove()
            return
        for widget in self._classification_hidden_widgets:
            widget.grid()

    def _on_scroll_canvas_configure(self, event: tk.Event) -> None:
        if self._scroll_canvas is not None and self._scroll_window_id is not None:
            self._scroll_canvas.itemconfigure(self._scroll_window_id, width=event.width)

    def destroy(self) -> None:
        self._unbind_scroll_events(None)
        self._scroll_canvas = None
        super().destroy()

    def _bind_scroll_events(self, _event: tk.Event) -> None:
        self.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_scroll_events(self, _event: tk.Event) -> None:
        self.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        canvas = self._scroll_canvas
        if canvas is None:
            return
        try:
            if int(canvas.winfo_exists()) != 1:
                self._scroll_canvas = None
                return
            canvas.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:
            self._scroll_canvas = None

    def _configure_scroll_geometry(self) -> None:
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        target_width = min(max(self.winfo_reqwidth(), 720), max(720, screen_width - 120))
        target_height = min(max(560, int(screen_height * 0.8)), self.winfo_reqheight())
        self.geometry(f"{target_width}x{target_height}")
        self.minsize(720, 560)

    def _browse_storage_folder(self) -> None:
        directory = filedialog.askdirectory(parent=self, title="Wybierz folder dla projektów")
        if directory:
            self.storage_folder_var.set(directory)

    def _browse_label_preview(self) -> None:
        file_path = filedialog.askopenfilename(
            parent=self,
            title="Wybierz zdjęcie przykładowe",
            filetypes=[("Obrazy", "*.png *.jpg *.jpeg *.bmp *.gif *.webp")],
        )
        if file_path:
            self.label_preview_var.set(file_path)

    def _on_preview_type_changed(self, *_args) -> None:
        self._preview_points = []
        self._preview_dragging_bbox = False
        self._update_preview_tools()
        self._update_preview_status()
        self._refresh_preview_canvas()

    def _on_preview_source_changed(self, *_args) -> None:
        self._preview_points = []
        self._preview_dragging_bbox = False
        self._update_preview_status()
        self._refresh_preview_canvas()

    def _on_skeleton_points_changed(self, *_args) -> None:
        if self.label_type_var.get() != "Skeleton":
            return
        max_points = self._get_skeleton_point_count()
        if len(self._preview_points) > max_points:
            self._preview_points = self._preview_points[:max_points]
        self._update_preview_status()
        self._refresh_preview_canvas()

    def _update_preview_tools(self) -> None:
        if self.label_type_var.get() == "Skeleton":
            self.skeleton_points_spinbox.state(["!disabled"])
        else:
            self.skeleton_points_spinbox.state(["disabled"])

    def _refresh_preview_canvas(self) -> None:
        self.preview_canvas.delete("all")
        self._preview_photo = None
        self._preview_box = None

        preview_path = self.label_preview_var.get().strip()
        if not preview_path:
            self.preview_canvas.create_text(
                self.PREVIEW_CANVAS_SIZE[0] / 2,
                self.PREVIEW_CANVAS_SIZE[1] / 2,
                text="Wybierz zdjęcie przykładowe, aby zobaczyć podgląd.",
                fill="#e5e7eb",
                width=320,
                justify="center",
            )
            return

        if Image is None or ImageTk is None or ImageOps is None:
            self.preview_canvas.create_text(
                self.PREVIEW_CANVAS_SIZE[0] / 2,
                self.PREVIEW_CANVAS_SIZE[1] / 2,
                text="Brak Pillow. Nie mogę wyrenderować podglądu obrazu.",
                fill="#e5e7eb",
                width=320,
                justify="center",
            )
            return

        image_file = Path(preview_path)
        if not image_file.exists():
            self.preview_canvas.create_text(
                self.PREVIEW_CANVAS_SIZE[0] / 2,
                self.PREVIEW_CANVAS_SIZE[1] / 2,
                text="Wybrane zdjęcie nie istnieje.",
                fill="#e5e7eb",
            )
            return

        try:
            image = Image.open(image_file)
            image = ImageOps.contain(image, self.PREVIEW_CANVAS_SIZE)
        except OSError:
            self.preview_canvas.create_text(
                self.PREVIEW_CANVAS_SIZE[0] / 2,
                self.PREVIEW_CANVAS_SIZE[1] / 2,
                text="Nie udało się odczytać wybranego obrazu.",
                fill="#e5e7eb",
            )
            return

        self._preview_photo = ImageTk.PhotoImage(image)
        x0 = (self.PREVIEW_CANVAS_SIZE[0] - image.size[0]) / 2
        y0 = (self.PREVIEW_CANVAS_SIZE[1] - image.size[1]) / 2
        x1 = x0 + image.size[0]
        y1 = y0 + image.size[1]
        self._preview_box = (x0, y0, x1, y1)
        self.preview_canvas.create_image(self.PREVIEW_CANVAS_SIZE[0] / 2, self.PREVIEW_CANVAS_SIZE[1] / 2, image=self._preview_photo)
        self.preview_canvas.create_rectangle(x0, y0, x1, y1, outline="#94a3b8")
        self._draw_preview_overlay()

    def _draw_preview_overlay(self) -> None:
        if self._preview_box is None:
            return

        canvas_points = [self._to_canvas_point(point) for point in self._preview_points]
        label_type = self.label_type_var.get()

        if label_type == "Bounding box":
            if len(canvas_points) == 1:
                x_pos, y_pos = canvas_points[0]
                self.preview_canvas.create_oval(x_pos - 4, y_pos - 4, x_pos + 4, y_pos + 4, fill="#ef4444", outline="")
            elif len(canvas_points) >= 2:
                (x0, y0), (x1, y1) = canvas_points[:2]
                self.preview_canvas.create_rectangle(x0, y0, x1, y1, outline="#ef4444", width=2)
            return

        if label_type in {"Polyline", "Skeleton", "Polygon", "Segmentacja (maska)"} and len(canvas_points) >= 2:
            flat_points = [value for point in canvas_points for value in point]
            self.preview_canvas.create_line(*flat_points, fill="#22c55e", width=2)
            if label_type in {"Polygon", "Segmentacja (maska)"} and len(canvas_points) >= 3:
                first_x, first_y = canvas_points[0]
                last_x, last_y = canvas_points[-1]
                self.preview_canvas.create_line(last_x, last_y, first_x, first_y, fill="#22c55e", width=2)

        for index, (x_pos, y_pos) in enumerate(canvas_points, start=1):
            self.preview_canvas.create_oval(x_pos - 5, y_pos - 5, x_pos + 5, y_pos + 5, fill="#ef4444", outline="#ffffff")
            if label_type == "Skeleton":
                self.preview_canvas.create_text(x_pos + 10, y_pos - 10, text=str(index), fill="#ffffff", anchor="w")

    def _on_preview_canvas_press(self, event: tk.Event) -> None:
        point = self._to_normalized_point(event.x, event.y)
        if point is None:
            return

        label_type = self.label_type_var.get()
        if label_type == "Bounding box":
            self._preview_points = [point, dict(point)]
            self._preview_dragging_bbox = True
            self.preview_status_var.set("Przeciagaj myszka, aby okreslic przeciwlegly rog bounding boxa.")
            self._refresh_preview_canvas()
            return

        self._on_preview_canvas_click(event)

    def _on_preview_canvas_click(self, event: tk.Event) -> None:
        point = self._to_normalized_point(event.x, event.y)
        if point is None:
            return

        label_type = self.label_type_var.get()
        if label_type == "Klasyfikacja":
            self.preview_status_var.set("Typ klasyfikacja nie wymaga klikanego szkicu. Zdjęcie działa tu jako referencja.")
            return

        if label_type == "Point":
            self._preview_points = [point]
        elif label_type == "Bounding box":
            self.preview_status_var.set("Bounding box rysuje sie przez przeciaganie myszka na podgladzie.")
            return
        else:
            if label_type == "Skeleton" and len(self._preview_points) >= self._get_skeleton_point_count():
                self.preview_status_var.set("Skeleton ma już komplet punktów. Użyj Cofnij albo Wyczyść szkic.")
                return
            self._preview_points.append(point)

        self._update_preview_status()
        self._refresh_preview_canvas()

    def _on_preview_canvas_drag(self, event: tk.Event) -> None:
        if not self._preview_dragging_bbox or len(self._preview_points) < 2:
            return
        point = self._to_normalized_point(event.x, event.y)
        if point is None:
            return
        self._preview_points[1] = point
        self._refresh_preview_canvas()

    def _on_preview_canvas_release(self, _event: tk.Event) -> None:
        if not self._preview_dragging_bbox:
            return
        self._preview_dragging_bbox = False
        if len(self._preview_points) >= 2:
            start_point = self._preview_points[0]
            end_point = self._preview_points[1]
            if start_point["x"] == end_point["x"] and start_point["y"] == end_point["y"]:
                self._preview_points = []
        self._update_preview_status()
        self._refresh_preview_canvas()

    def _undo_preview_step(self) -> None:
        if not self._preview_points:
            return
        if self.label_type_var.get() == "Bounding box" and len(self._preview_points) == 2:
            self._preview_points = []
            self._preview_dragging_bbox = False
            self._update_preview_status()
            self._refresh_preview_canvas()
            return
        self._preview_points.pop()
        self._preview_dragging_bbox = False
        self._update_preview_status()
        self._refresh_preview_canvas()

    def _clear_preview_definition(self) -> None:
        self._preview_points = []
        self._preview_dragging_bbox = False
        self._update_preview_status()
        self._refresh_preview_canvas()

    def _to_normalized_point(self, canvas_x: float, canvas_y: float) -> dict[str, float] | None:
        if self._preview_box is None:
            return None
        x0, y0, x1, y1 = self._preview_box
        if canvas_x < x0 or canvas_x > x1 or canvas_y < y0 or canvas_y > y1:
            return None
        width = max(1.0, x1 - x0)
        height = max(1.0, y1 - y0)
        return {
            "x": round((canvas_x - x0) / width, 4),
            "y": round((canvas_y - y0) / height, 4),
        }

    def _to_canvas_point(self, point: dict[str, float]) -> tuple[float, float]:
        x0, y0, x1, y1 = self._preview_box or (0.0, 0.0, 1.0, 1.0)
        return (x0 + point["x"] * (x1 - x0), y0 + point["y"] * (y1 - y0))

    def _get_skeleton_point_count(self) -> int:
        try:
            return max(2, int(self.skeleton_points_var.get()))
        except (TypeError, tk.TclError, ValueError):
            return 4

    def _update_preview_status(self) -> None:
        preview_path = self.label_preview_var.get().strip()
        label_type = self.label_type_var.get()
        point_count = len(self._preview_points)
        if self._is_classification_project() or label_type == "Klasyfikacja":
            self.preview_status_var.set("Projekt klasyfikacyjny nie wymaga zdjęcia przykładowego ani szkicu etykiety.")
            return
        if not preview_path:
            self.preview_status_var.set("Wybierz zdjęcie przykładowe, aby zobaczyć podgląd i przygotować szkic etykiety.")
            return
        if label_type == "Skeleton":
            expected = self._get_skeleton_point_count()
            self.preview_status_var.set(f"Klikaj kolejne punkty skeletonu: {point_count}/{expected}.")
            return
        if label_type == "Bounding box":
            self.preview_status_var.set("Nacisnij i przeciagnij myszka, aby narysowac bounding box na obrazie.")
            return
        if label_type in {"Polygon", "Segmentacja (maska)"}:
            self.preview_status_var.set(f"Klikaj wierzchołki obszaru. Aktualnie: {point_count} punktów.")
            return
        if label_type == "Polyline":
            self.preview_status_var.set(f"Klikaj kolejne punkty linii. Aktualnie: {point_count} punktów.")
            return
        if label_type == "Point":
            self.preview_status_var.set("Kliknij pojedynczy punkt referencyjny na obrazie.")
            return
        self.preview_status_var.set("Zaznacz szkic etykiety na obrazie.")

    def _build_preview_definition(self) -> dict[str, object] | None:
        label_type = self.label_type_var.get()
        if label_type == "Klasyfikacja":
            return None
        if not self._preview_points:
            return None

        payload: dict[str, object] = {
            "type": label_type,
            "points": list(self._preview_points),
        }
        if label_type == "Skeleton":
            payload["point_count"] = self._get_skeleton_point_count()
        return payload

    def _validate_preview_definition(
        self,
        preview_path: str | None,
        preview_definition: dict[str, object] | None,
    ) -> str | None:
        label_type = self.label_type_var.get()
        if not preview_path or label_type == "Klasyfikacja":
            return None
        if preview_definition is None:
            return "Po wybraniu zdjęcia przykładowego zaznacz szkic etykiety na podglądzie."

        points = preview_definition.get("points", [])
        point_count = len(points) if isinstance(points, list) else 0
        if label_type == "Skeleton" and point_count != self._get_skeleton_point_count():
            return f"Skeleton musi mieć dokładnie {self._get_skeleton_point_count()} punktów."
        if label_type == "Bounding box" and point_count != 2:
            return "Bounding box wymaga przeciagniecia myszka od jednego rogu do przeciwleglego."
        if label_type == "Point" and point_count != 1:
            return "Typ Point wymaga dokładnie jednego punktu."
        if label_type == "Polyline" and point_count < 2:
            return "Polyline wymaga co najmniej dwóch punktów."
        if label_type in {"Polygon", "Segmentacja (maska)"} and point_count < 3:
            return "Polygon i maska wymagają co najmniej trzech punktów."
        return None

    def _describe_preview_definition(self, preview_definition: dict[str, object] | None) -> str:
        if not preview_definition:
            return "brak"
        points = preview_definition.get("points", [])
        point_count = len(points) if isinstance(points, list) else 0
        return f"{point_count} pkt"

    def _add_current_label(self) -> None:
        name = self.label_name_var.get().strip()
        if not name:
            messagebox.showwarning("Brak danych", "Podaj nazwę etykiety.", parent=self)
            return

        preview_path = None if self._is_classification_project() else (self.label_preview_var.get().strip() or None)
        if preview_path and not Path(preview_path).exists():
            messagebox.showwarning("Nieprawidłowa ścieżka", "Wybrane zdjęcie przykładowe nie istnieje.", parent=self)
            return

        preview_definition = None if self._is_classification_project() else self._build_preview_definition()
        validation_error = self._validate_preview_definition(preview_path, preview_definition)
        if validation_error:
            messagebox.showwarning("Niepełny szkic", validation_error, parent=self)
            return

        self.labels.append(
            {
                "name": name,
                "label_type": self.label_type_var.get(),
                "preview_image_path": preview_path,
                "preview_definition": preview_definition,
            }
        )
        self._refresh_labels_tree()
        self._clear_label_form()

    def _clear_label_form(self) -> None:
        self.label_name_var.set("")
        self.label_preview_var.set("")
        self.label_type_var.set(self._get_available_label_types_for_project()[0])
        self.skeleton_points_var.set(4)
        self._preview_points = []
        self._update_preview_status()
        self._refresh_preview_canvas()

    def _remove_selected_label(self) -> None:
        selected = self.labels_tree.selection()
        if not selected:
            return
        label_index = int(selected[0])
        del self.labels[label_index]
        self._refresh_labels_tree()

    def _refresh_labels_tree(self) -> None:
        for item_id in self.labels_tree.get_children():
            self.labels_tree.delete(item_id)
        for index, label in enumerate(self.labels):
            preview_name = Path(label["preview_image_path"]).name if label["preview_image_path"] else "-"
            self.labels_tree.insert(
                "",
                "end",
                iid=str(index),
                text=label["name"],
                values=(label["label_type"], preview_name, self._describe_preview_definition(label.get("preview_definition"))),
            )

    def _save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Brak danych", "Podaj nazwę projektu.", parent=self)
            return
        if not self.labels:
            messagebox.showwarning("Brak danych", "Dodaj przynajmniej jedną etykietę startową.", parent=self)
            return
        if not self.storage_folder_var.get().strip():
            messagebox.showwarning("Brak danych", "Wybierz folder, w którym mają być zapisywane projekty.", parent=self)
            return
        if self._is_classification_project() and any(label["label_type"] != "Klasyfikacja" for label in self.labels):
            messagebox.showwarning(
                "Nieprawidłowe etykiety",
                "Projekt typu Klasyfikacja może zawierać wyłącznie etykiety typu Klasyfikacja.",
                parent=self,
            )
            return
        self.result = {
            "name": name,
            "project_type": self.project_type_var.get(),
            "storage_folder": self.storage_folder_var.get().strip(),
            "labels": list(self.labels),
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


class BatchProgressDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str, total_steps: int) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.columnconfigure(0, weight=1)

        self.total_steps = max(1, int(total_steps))
        self.status_var = tk.StringVar(value="Przygotowanie autolabelingu...")
        self.counter_var = tk.StringVar(value=f"0 / {self.total_steps}")
        self.details_var = tk.StringVar(value="")

        body = ttk.Frame(self, padding=18)
        body.grid(sticky="nsew")
        body.columnconfigure(0, weight=1)

        ttk.Label(body, textvariable=self.status_var, justify="left", wraplength=420).grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(body, mode="determinate", maximum=self.total_steps, value=0, length=420)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(12, 8))
        ttk.Label(body, textvariable=self.counter_var).grid(row=2, column=0, sticky="w")
        ttk.Label(body, textvariable=self.details_var, justify="left", wraplength=420).grid(row=3, column=0, sticky="w", pady=(8, 0))

        self.after_idle(lambda: center_window_on_screen(self))
        self._refresh()

    def set_indeterminate(self, enabled: bool) -> None:
        if enabled:
            self.progress.configure(mode="indeterminate")
            self.progress.start(10)
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate")
        self._refresh()

    def update_progress(self, completed_steps: int, current_image_name: str, total_annotations: int) -> None:
        bounded_steps = max(0, min(int(completed_steps), self.total_steps))
        self.progress.configure(value=bounded_steps)
        self.status_var.set(f"Autolabeling obrazu {bounded_steps}/{self.total_steps}: {current_image_name}")
        self.counter_var.set(f"{bounded_steps} / {self.total_steps}")
        self.details_var.set(f"Dodane annotacje lacznie: {total_annotations}")
        self._refresh()

    def _refresh(self) -> None:
        self.update_idletasks()
        self.update()

    def close(self) -> None:
        if self.winfo_exists():
            self.progress.stop()
            self.grab_release()
            self.destroy()


class ModelInferenceDialog(BaseDialog):
    MODE_DEFAULTS = {
        "Klasyfikacja": {"input_width": 224, "input_height": 224, "confidence": 0.25, "iou": 0.45},
        "Detekcja obiektow": {"input_width": 640, "input_height": 640, "confidence": 0.25, "iou": 0.45},
        "Pose / Keypointy": {"input_width": 640, "input_height": 640, "confidence": 0.25, "iou": 0.45},
        "Segmentacja": {"input_width": 640, "input_height": 640, "confidence": 0.25, "iou": 0.45},
    }

    def __init__(self, parent: tk.Misc, available_modes: list[str], initial_config: dict[str, object] | None = None) -> None:
        super().__init__(parent, "Uruchom model")
        self.available_modes = available_modes
        initial_config = dict(initial_config or {})
        self._preserve_initial_mode_defaults = bool(initial_config)
        requested_mode = str(initial_config.get("mode") or "").strip()
        first_mode = requested_mode if requested_mode in available_modes else (available_modes[0] if available_modes else "")
        defaults = self.MODE_DEFAULTS.get(first_mode, {"input_width": 640, "input_height": 640, "confidence": 0.25, "iou": 0.45})
        self.mode_var = tk.StringVar(value=first_mode)
        self.model_path_var = tk.StringVar(value=str(initial_config.get("model_path") or ""))
        runtime_label = AppService.MODEL_RUNTIME_OPTIONS.get(
            str(initial_config.get("runtime") or "auto").strip().casefold(),
            AppService.MODEL_RUNTIME_OPTIONS["auto"],
        )
        self.runtime_var = tk.StringVar(value=runtime_label)
        self.labels_path_var = tk.StringVar(value=str(initial_config.get("labels_path") or ""))
        self.input_width_var = tk.IntVar(value=int(initial_config.get("input_width") or defaults["input_width"]))
        self.input_height_var = tk.IntVar(value=int(initial_config.get("input_height") or defaults["input_height"]))
        self.confidence_var = tk.DoubleVar(value=float(initial_config.get("confidence_threshold") or defaults["confidence"]))
        self.iou_var = tk.DoubleVar(value=float(initial_config.get("iou_threshold") or defaults["iou"]))
        self.summary_var = tk.StringVar(
            value="Wybierz model .onnx, .pt/.pth/.ts/.jit/.ckpt albo TensorFlow (.h5/.keras/.tflite lub katalog SavedModel). Plik klas jest opcjonalny - bez niego zostanie uzyta kolejnosc etykiet projektu."
        )
        self._build()
        self.model_path_var.trace_add("write", self._on_model_path_changed)

    def _build(self) -> None:
        container = ttk.Frame(self, padding=18)
        container.grid(sticky="nsew")
        container.columnconfigure(0, weight=1)

        ttk.Label(container, text="Tryb inferencji").grid(row=0, column=0, sticky="w")
        self.mode_combo = ttk.Combobox(
            container,
            textvariable=self.mode_var,
            values=self.available_modes,
            state="readonly",
            width=38,
        )
        self.mode_combo.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12))
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_mode_changed())

        ttk.Label(container, text="Plik modelu").grid(row=2, column=0, sticky="w")
        ttk.Entry(container, textvariable=self.model_path_var, width=42).grid(row=3, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(container, text="Wybierz model", command=self._browse_model).grid(row=3, column=1, sticky="ew", padx=(8, 0))

        ttk.Label(container, text="Implementacja modelu").grid(row=4, column=0, sticky="w", pady=(12, 0))
        self.runtime_combo = ttk.Combobox(
            container,
            textvariable=self.runtime_var,
            values=AppService.get_model_runtime_labels_for_path(self.model_path_var.get().strip()),
            state="readonly",
            width=38,
        )
        self.runtime_combo.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.runtime_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_mode_changed())

        ttk.Label(container, text="Plik klas (opcjonalny)").grid(row=6, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(container, textvariable=self.labels_path_var, width=42).grid(row=7, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(container, text="Wybierz klasy", command=self._browse_labels).grid(row=7, column=1, sticky="ew", padx=(8, 0))

        size_frame = ttk.Frame(container)
        size_frame.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Label(size_frame, text="Input width").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(size_frame, from_=16, to=4096, textvariable=self.input_width_var, width=8).grid(row=0, column=1, padx=(8, 16))
        ttk.Label(size_frame, text="Input height").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(size_frame, from_=16, to=4096, textvariable=self.input_height_var, width=8).grid(row=0, column=3, padx=(8, 0))

        threshold_frame = ttk.Frame(container)
        threshold_frame.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Label(threshold_frame, text="Confidence").grid(row=0, column=0, sticky="w")
        ttk.Entry(threshold_frame, textvariable=self.confidence_var, width=8).grid(row=0, column=1, padx=(8, 16))
        self.iou_label = ttk.Label(threshold_frame, text="IOU")
        self.iou_label.grid(row=0, column=2, sticky="w")
        self.iou_entry = ttk.Entry(threshold_frame, textvariable=self.iou_var, width=8)
        self.iou_entry.grid(row=0, column=3, padx=(8, 0))

        ttk.Label(container, textvariable=self.summary_var, justify="left", wraplength=420).grid(
            row=10,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(12, 0),
        )

        actions = ttk.Frame(container)
        actions.grid(row=11, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(actions, text="Anuluj", command=self._close).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Uruchom model", command=self._save).grid(row=0, column=1)
        self._refresh_runtime_options()
        self._on_mode_changed()

    def _browse_model(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Wybierz model",
            filetypes=[("Modele inferencyjne", "*.onnx *.pt *.pth *.ts *.jit *.ckpt *.torchscript *.h5 *.keras *.tflite"), ("Wszystkie", "*.*")],
        )
        if selected:
            self.model_path_var.set(selected)

    def _browse_labels(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Wybierz plik klas",
            filetypes=[("Pliki tekstowe", "*.txt *.names"), ("Wszystkie", "*.*")],
        )
        if selected:
            self.labels_path_var.set(selected)

    def _on_model_path_changed(self, *_args) -> None:
        self._refresh_runtime_options()
        self._on_mode_changed()

    def _refresh_runtime_options(self) -> None:
        runtime_labels = AppService.get_model_runtime_labels_for_path(self.model_path_var.get().strip())
        current_runtime = self.runtime_var.get().strip()
        self.runtime_combo.configure(values=runtime_labels)
        if current_runtime not in runtime_labels:
            self.runtime_var.set(runtime_labels[0])

    def _on_mode_changed(self) -> None:
        mode = self.mode_var.get().strip()
        runtime_label = self.runtime_var.get().strip() or AppService.MODEL_RUNTIME_OPTIONS["auto"]
        defaults = self.MODE_DEFAULTS.get(mode)
        if defaults is not None and not self._preserve_initial_mode_defaults:
            self.input_width_var.set(int(defaults["input_width"]))
            self.input_height_var.set(int(defaults["input_height"]))
            self.confidence_var.set(float(defaults["confidence"]))
            self.iou_var.set(float(defaults["iou"]))
        self._preserve_initial_mode_defaults = False
        if mode == "Klasyfikacja":
            self.summary_var.set(
                f"Model zwroci jedna etykiete dla aktualnego obrazu. Wybrana implementacja: {runtime_label}."
            )
            self.iou_label.grid_remove()
            self.iou_entry.grid_remove()
        elif mode == "Pose / Keypointy":
            self.summary_var.set(
                f"Model zwroci keypointy dla aktualnego obrazu i zapisze je jako Point albo Skeleton. Wybrana implementacja: {runtime_label}."
            )
            self.iou_label.grid()
            self.iou_entry.grid()
        elif mode == "Segmentacja":
            self.summary_var.set(
                f"Model zwroci maske lub obrys dla aktualnego obrazu i zapisze go jako Polygon albo Segmentacja (maska). Wybrana implementacja: {runtime_label}."
            )
            self.iou_label.grid()
            self.iou_entry.grid()
        else:
            self.summary_var.set(
                f"Model zwroci bounding boxy dla aktualnego obrazu. Wybrana implementacja: {runtime_label}."
            )
            self.iou_label.grid()
            self.iou_entry.grid()

    def _save(self) -> None:
        model_path = self.model_path_var.get().strip()
        labels_path = self.labels_path_var.get().strip()
        if not self.mode_var.get().strip():
            messagebox.showwarning("Model", "Wybierz tryb inferencji.", parent=self)
            return
        if not model_path:
            messagebox.showwarning("Model", "Wybierz plik modelu.", parent=self)
            return
        if not Path(model_path).exists():
            messagebox.showwarning("Model", "Wybrany plik modelu nie istnieje.", parent=self)
            return
        if labels_path and not Path(labels_path).exists():
            messagebox.showwarning("Model", "Wybrany plik klas nie istnieje.", parent=self)
            return
        if self.input_width_var.get() < 16 or self.input_height_var.get() < 16:
            messagebox.showwarning("Model", "Input width i height musza byc dodatnie.", parent=self)
            return
        if not 0 <= float(self.confidence_var.get()) <= 1:
            messagebox.showwarning("Model", "Confidence musi byc w zakresie 0-1.", parent=self)
            return
        if self.mode_var.get() != "Klasyfikacja" and not 0 <= float(self.iou_var.get()) <= 1:
            messagebox.showwarning("Model", "IOU musi byc w zakresie 0-1.", parent=self)
            return

        self.result = {
            "mode": self.mode_var.get().strip(),
            "model_path": model_path,
            "runtime": AppService.get_model_runtime_key_from_label(self.runtime_var.get().strip()),
            "labels_path": labels_path or None,
            "input_width": int(self.input_width_var.get()),
            "input_height": int(self.input_height_var.get()),
            "confidence_threshold": float(self.confidence_var.get()),
            "iou_threshold": float(self.iou_var.get()),
        }
        self.destroy()


class CreateTaskDialog(BaseDialog):
    IMPORT_SOURCE_OPTIONS = {
        "Folder ze zdjęciami": "folder",
        "Dataset z etykietami": "dataset",
        "Pojedyncze zdjęcia": "images",
        "Plik wideo": "video",
    }

    def __init__(self, parent: tk.Misc, initial_config: dict[str, object] | None = None) -> None:
        super().__init__(parent, "Create New Task")
        self.resizable(True, True)
        self.geometry("700x380")
        self.minsize(620, 340)
        initial_config = dict(initial_config or {})
        default_source_type = next(iter(self.IMPORT_SOURCE_OPTIONS))
        requested_source_type = str(initial_config.get("source_type") or "").strip()
        initial_source_type = requested_source_type if requested_source_type in self.IMPORT_SOURCE_OPTIONS else default_source_type
        requested_dataset_format = str(initial_config.get("dataset_format") or "").strip()
        initial_dataset_format = (
            requested_dataset_format
            if requested_dataset_format in AppService.DATASET_IMPORT_FORMATS
            else (AppService.DATASET_IMPORT_FORMATS[0] if AppService.DATASET_IMPORT_FORMATS else "")
        )
        try:
            requested_stride = int(initial_config.get("frame_stride") or 30)
        except (TypeError, ValueError):
            requested_stride = 30
        initial_stride = requested_stride if requested_stride >= 1 else 30

        self.name_var = tk.StringVar()
        self.source_path_var = tk.StringVar(value=str(initial_config.get("source_path") or ""))
        self.source_type_var = tk.StringVar(value=initial_source_type)
        self.dataset_format_var = tk.StringVar(value=initial_dataset_format)
        self.frame_stride_var = tk.IntVar(value=initial_stride)
        self.images: list[str] = []
        configured_source_paths = initial_config.get("source_paths")
        self.source_paths: list[str] = [
            str(path).strip()
            for path in (configured_source_paths if isinstance(configured_source_paths, list) else [])
            if str(path).strip()
        ]
        # Keep backward compatibility with older session payloads that stored only one source path.
        if not self.source_paths and self.source_path_var.get().strip() and self._current_import_mode() in {"folder", "video"}:
            self.source_paths = [self.source_path_var.get().strip()]
        self.selection_summary_var = tk.StringVar(value="Nie wybrano jeszcze źródła danych.")
        self._build()

    def _build(self) -> None:
        container = ttk.Frame(self, padding=18)
        container.grid(sticky="nsew")
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=0)

        ttk.Label(container, text="Nazwa taska").grid(row=0, column=0, sticky="w")
        ttk.Entry(container, textvariable=self.name_var, width=40).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        ttk.Label(container, text="Źródło importu").grid(row=2, column=0, columnspan=2, sticky="w")
        self.source_type_combo = ttk.Combobox(
            container,
            textvariable=self.source_type_var,
            values=list(self.IMPORT_SOURCE_OPTIONS.keys()),
            state="readonly",
            width=38,
        )
        self.source_type_combo.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 12))
        self.source_type_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_source_mode())

        self.source_label = ttk.Label(container, text="Folder z obrazami lub datasetem")
        self.source_label.grid(row=4, column=0, sticky="w")
        self.source_entry = ttk.Entry(container, textvariable=self.source_path_var, width=40)
        self.source_entry.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        self.source_button = ttk.Button(container, text="Wybierz", command=self._browse_source)
        self.source_button.grid(row=5, column=1, sticky="ew", padx=(8, 0))

        self.images_button = ttk.Button(container, text="Wybierz zdjęcia", command=self._browse_images)
        self.images_button.grid(row=6, column=1, sticky="ew", padx=(8, 0), pady=(12, 0))
        self.images_summary = ttk.Label(container, textvariable=self.selection_summary_var, justify="left", wraplength=320)
        self.images_summary.grid(row=6, column=0, sticky="ew", pady=(12, 0))

        self.dataset_format_label = ttk.Label(container, text="Format datasetu")
        self.dataset_format_combo = ttk.Combobox(
            container,
            textvariable=self.dataset_format_var,
            values=AppService.DATASET_IMPORT_FORMATS,
            state="readonly",
            width=38,
        )
        self.dataset_format_label.grid(row=7, column=0, sticky="w", pady=(12, 0))
        self.dataset_format_combo.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        self.frame_stride_label = ttk.Label(container, text="Zapisz co N-tą klatkę")
        self.frame_stride_spinbox = ttk.Spinbox(container, from_=1, to=500, textvariable=self.frame_stride_var, width=10)
        self.frame_stride_label.grid(row=9, column=0, sticky="w", pady=(12, 0))
        self.frame_stride_spinbox.grid(row=9, column=1, sticky="w", pady=(12, 0))

        actions = ttk.Frame(container)
        actions.grid(row=10, column=0, columnspan=2, pady=(16, 0))
        ttk.Button(actions, text="Anuluj", command=self._close).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Utwórz task", command=self._save).pack(side="left")

        self._update_source_mode()

    def _browse_source(self) -> None:
        mode = self._current_import_mode()
        if mode == "video":
            selected = filedialog.askopenfilenames(
                parent=self,
                title="Wybierz pliki wideo",
                filetypes=[("Wideo", "*.mp4 *.avi *.mov *.mkv *.webm"), ("Wszystkie", "*.*")],
            )
            if not selected:
                return
            self.source_paths = self._merge_unique_paths(self.source_paths, list(selected))
            self.source_path_var.set(self.source_paths[0] if self.source_paths else "")
            if not self.name_var.get().strip() and self.source_paths:
                self.name_var.set(Path(self.source_paths[0]).stem)
            self._update_source_mode()
            return

        if mode == "folder":
            directory = filedialog.askdirectory(
                parent=self,
                title="Wybierz folder ze zdjęciami",
            )
            if not directory:
                return
            self.source_paths = self._merge_unique_paths(self.source_paths, [directory])
            self.source_path_var.set(self.source_paths[0] if self.source_paths else "")
            if not self.name_var.get().strip() and self.source_paths:
                self.name_var.set(Path(self.source_paths[0]).name)
            self._update_source_mode()
            return

        directory = filedialog.askdirectory(
            parent=self,
            title="Wybierz folder datasetu",
        )
        if not directory:
            return
        self.source_paths = []
        self.source_path_var.set(directory)
        if not self.name_var.get().strip():
            self.name_var.set(Path(directory).name)
        self._update_source_mode()

    def _clear_selection(self) -> None:
        mode = self._current_import_mode()
        if mode == "images":
            self.images = []
        elif mode in {"folder", "video"}:
            self.source_paths = []
            self.source_path_var.set("")
        elif mode == "dataset":
            self.source_path_var.set("")
        self._update_source_mode()

    def _merge_unique_paths(self, existing: list[str], incoming: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for raw_path in [*existing, *incoming]:
            candidate = str(raw_path).strip()
            if not candidate:
                continue
            normalized = str(Path(candidate).resolve())
            if normalized in seen:
                continue
            seen.add(normalized)
            merged.append(candidate)
        return merged

    def _browse_images(self) -> None:
        selected = filedialog.askopenfilenames(
            parent=self,
            title="Wybierz zdjęcia do taska",
            filetypes=[("Obrazy", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("Wszystkie", "*.*")],
        )
        if not selected:
            return
        self.images = self._merge_unique_paths(self.images, list(selected))
        if not self.name_var.get().strip() and self.images:
            first_parent = Path(self.images[0]).parent.name
            self.name_var.set(first_parent or "task")
        self._update_source_mode()

    def _current_import_mode(self) -> str:
        return self.IMPORT_SOURCE_OPTIONS.get(self.source_type_var.get(), "folder")

    def _update_source_mode(self) -> None:
        mode = self._current_import_mode()
        folder_mode = mode == "folder"
        dataset_mode = mode == "dataset"
        image_mode = mode == "images"
        video_mode = mode == "video"

        if video_mode:
            source_label_text = "Pliki wideo"
        elif dataset_mode:
            source_label_text = "Folder datasetu"
        else:
            source_label_text = "Foldery ze zdjęciami"
        self.source_label.configure(text=source_label_text)
        self.source_entry.state(["!disabled"] if dataset_mode else ["disabled"])
        self.source_button.state(["!disabled"] if not image_mode else ["disabled"])
        self.images_button.state(["!disabled"])
        if dataset_mode:
            self.dataset_format_label.grid()
            self.dataset_format_combo.grid()
        else:
            self.dataset_format_label.grid_remove()
            self.dataset_format_combo.grid_remove()

        if video_mode:
            self.source_button.configure(text="Dodaj wideo")
            self.images_button.configure(text="Wyczyść wybór", command=self._clear_selection)
            self.frame_stride_label.grid()
            self.frame_stride_spinbox.grid()
        elif folder_mode:
            self.source_button.configure(text="Dodaj folder")
            self.images_button.configure(text="Wyczyść wybór", command=self._clear_selection)
            self.frame_stride_label.grid_remove()
            self.frame_stride_spinbox.grid_remove()
        elif dataset_mode:
            self.source_button.configure(text="Wybierz folder")
            self.images_button.configure(text="Wyczyść wybór", command=self._clear_selection)
            self.frame_stride_label.grid_remove()
            self.frame_stride_spinbox.grid_remove()
        else:
            self.source_button.configure(text="Wybierz folder")
            self.images_button.configure(text="Dodaj zdjęcia", command=self._browse_images)
            self.frame_stride_label.grid_remove()
            self.frame_stride_spinbox.grid_remove()

        if folder_mode:
            if self.source_paths:
                folder_names = ", ".join(Path(path).name for path in self.source_paths[:2])
                suffix = "" if len(self.source_paths) <= 2 else f" i jeszcze {len(self.source_paths) - 2}"
                self.selection_summary_var.set(f"Wybrano {len(self.source_paths)} foldery: {folder_names}{suffix}")
            else:
                self.selection_summary_var.set("Dodaj jeden lub więcej folderów ze zdjęciami bez etykiet.")
            return

        if dataset_mode:
            if self.source_path_var.get().strip():
                self.selection_summary_var.set(
                    f"Dataset: {Path(self.source_path_var.get().strip()).name} | format: {self.dataset_format_var.get()}"
                )
            else:
                self.selection_summary_var.set("Wybierz folder datasetu i format importu etykiet.")
            return

        if image_mode:
            if self.images:
                first_names = ", ".join(Path(path).name for path in self.images[:2])
                suffix = "" if len(self.images) <= 2 else f" i jeszcze {len(self.images) - 2}"
                self.selection_summary_var.set(f"Wybrano {len(self.images)} zdjęć: {first_names}{suffix}")
            else:
                self.selection_summary_var.set("Dodaj pojedyncze zdjęcia do zaimportowania.")
            return

        if self.source_paths:
            video_names = ", ".join(Path(path).name for path in self.source_paths[:2])
            suffix = "" if len(self.source_paths) <= 2 else f" i jeszcze {len(self.source_paths) - 2}"
            self.selection_summary_var.set(f"Wybrano {len(self.source_paths)} pliki wideo: {video_names}{suffix}")
        else:
            self.selection_summary_var.set("Dodaj jeden lub więcej plików wideo i ustaw odstęp między klatkami.")

    def _save(self) -> None:
        if not self.name_var.get().strip():
            messagebox.showwarning("Brak danych", "Podaj nazwę taska.", parent=self)
            return
        import_mode = self._current_import_mode()
        source_path = self.source_path_var.get().strip()
        image_paths = list(self.images)
        folder_paths = list(self.source_paths)
        video_paths = list(self.source_paths)
        if import_mode == "folder" and source_path and not folder_paths:
            folder_paths = [source_path]
        if import_mode == "video" and source_path and not video_paths:
            video_paths = [source_path]
        if import_mode == "folder" and not folder_paths:
            messagebox.showwarning("Brak danych", "Wybierz przynajmniej jeden folder ze zdjęciami.", parent=self)
            return
        if import_mode == "dataset" and not source_path:
            messagebox.showwarning("Brak danych", "Wybierz folder datasetu.", parent=self)
            return
        if import_mode == "dataset" and not self.dataset_format_var.get().strip():
            messagebox.showwarning("Brak danych", "Wybierz format datasetu do importu etykiet.", parent=self)
            return
        if import_mode == "images" and not image_paths:
            messagebox.showwarning("Brak danych", "Wybierz przynajmniej jedno zdjęcie.", parent=self)
            return
        if import_mode == "video" and not video_paths:
            messagebox.showwarning("Brak danych", "Wybierz przynajmniej jeden plik wideo.", parent=self)
            return
        if import_mode == "video" and self.frame_stride_var.get() < 1:
            messagebox.showwarning("Brak danych", "Odstęp między klatkami musi być dodatni.", parent=self)
            return
        self.result = {
            "task_name": self.name_var.get().strip(),
            "import_mode": import_mode,
            "dataset_folder": source_path if import_mode == "dataset" else (folder_paths[0] if folder_paths else ""),
            "dataset_folders": folder_paths if import_mode == "folder" else [],
            "dataset_format": self.dataset_format_var.get().strip() if import_mode == "dataset" else "",
            "image_paths": image_paths,
            "video_path": video_paths[0] if video_paths else "",
            "video_paths": video_paths if import_mode == "video" else [],
            "frame_stride": int(self.frame_stride_var.get()),
            "dialog_state": {
                "source_type": self.source_type_var.get().strip(),
                "source_path": source_path if import_mode == "dataset" else (folder_paths[0] if folder_paths else ""),
                "source_paths": folder_paths if import_mode == "folder" else (video_paths if import_mode == "video" else []),
                "dataset_format": self.dataset_format_var.get().strip(),
                "frame_stride": int(self.frame_stride_var.get()),
            },
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