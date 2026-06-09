from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk

from model.entities import ProjectDetails, ProjectSummary, SessionState, TaskSummary

try:
    from PIL import Image, ImageOps, ImageTk
except ImportError:
    Image = None
    ImageOps = None
    ImageTk = None


class AppView(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Annotatio")
        self.minsize(1200, 800)

        self._nav_callback = None
        self._create_project_callback = None
        self._export_project_callback = None
        self._open_project_callback = None
        self._back_to_projects_callback = None
        self._create_task_callback = None
        self._open_task_callback = None
        self._merge_projects_callback = None
        self._merge_tasks_callback = None
        self._add_annotation_callback = None
        self._toggle_annotation_callback = None
        self._delete_annotation_callback = None
        self._delete_image_callback = None
        self._auto_label_callback = None
        self._change_image_callback = None

        self.selected_project_id: int | None = None
        self.annotation_ids_by_row: dict[str, int] = {}
        self.current_task_annotation_labels: dict[str, int] = {}
        self._image_cache = None

        self._configure_style()
        self._build_shell()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Sidebar.TFrame", background="#1f2937")
        style.configure("Sidebar.TButton", background="#1f2937", foreground="#f9fafb", padding=10)
        style.map("Sidebar.TButton", background=[("active", "#374151")])
        style.configure("Card.TFrame", background="#f8fafc", relief="solid", borderwidth=1)
        style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("SubHeader.TLabel", font=("Segoe UI", 11, "bold"))

    def _build_shell(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = ttk.Frame(self, style="Sidebar.TFrame", width=180)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)
        self.sidebar.columnconfigure(0, weight=1)

        title = ttk.Label(self.sidebar, text="Annotatio", foreground="#f9fafb", background="#1f2937", font=("Segoe UI", 20, "bold"))
        title.grid(row=0, column=0, sticky="ew", padx=16, pady=(20, 24))

        nav_items = [
            ("Start", "home"),
            ("Projects", "projects"),
            ("Settings", "settings"),
            ("Info", "info"),
        ]
        for index, (label, page_name) in enumerate(nav_items, start=1):
            ttk.Button(
                self.sidebar,
                text=label,
                style="Sidebar.TButton",
                command=lambda value=page_name: self._nav_callback and self._nav_callback(value),
            ).grid(row=index, column=0, sticky="ew", padx=12, pady=4)

        self.content = ttk.Frame(self, padding=20)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

    def apply_session_state(self, session: SessionState) -> None:
        self.geometry(f"{session.window_width}x{session.window_height}")

    def set_navigation_callback(self, callback) -> None:
        self._nav_callback = callback

    def set_create_project_callback(self, callback) -> None:
        self._create_project_callback = callback

    def set_export_project_callback(self, callback) -> None:
        self._export_project_callback = callback

    def set_open_project_callback(self, callback) -> None:
        self._open_project_callback = callback

    def set_back_to_projects_callback(self, callback) -> None:
        self._back_to_projects_callback = callback

    def set_create_task_callback(self, callback) -> None:
        self._create_task_callback = callback

    def set_open_task_callback(self, callback) -> None:
        self._open_task_callback = callback

    def set_merge_projects_callback(self, callback) -> None:
        self._merge_projects_callback = callback

    def set_merge_tasks_callback(self, callback) -> None:
        self._merge_tasks_callback = callback

    def set_add_annotation_callback(self, callback) -> None:
        self._add_annotation_callback = callback

    def set_toggle_annotation_callback(self, callback) -> None:
        self._toggle_annotation_callback = callback

    def set_delete_annotation_callback(self, callback) -> None:
        self._delete_annotation_callback = callback

    def set_delete_image_callback(self, callback) -> None:
        self._delete_image_callback = callback

    def set_auto_label_callback(self, callback) -> None:
        self._auto_label_callback = callback

    def set_change_image_callback(self, callback) -> None:
        self._change_image_callback = callback

    def set_close_callback(self, callback) -> None:
        self.protocol("WM_DELETE_WINDOW", callback)

    def get_selected_project_id(self) -> int | None:
        return self.selected_project_id

    def show_start_page(self, description: str) -> None:
        frame = self._reset_content()
        ttk.Label(frame, text="Warstwowa aplikacja do annotacji", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            frame,
            text=description,
            justify="left",
            wraplength=820,
        ).grid(row=1, column=0, sticky="nw", pady=(20, 0))

    def show_projects_page(self, projects: list[ProjectSummary]) -> None:
        frame = self._reset_content()
        frame.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 16))

        ttk.Label(toolbar, text="Projects", style="Header.TLabel").pack(side="left")
        ttk.Button(toolbar, text="Create New Project", command=self._create_project_callback).pack(side="right", padx=(8, 0))
        ttk.Button(toolbar, text="Merge Projects", command=self._merge_projects_callback).pack(side="right", padx=(8, 0))
        ttk.Button(toolbar, text="Export Dataset", command=self._export_project_callback).pack(side="right")

        canvas = tk.Canvas(frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        scrollable.bind(
            "<Configure>",
            lambda event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        scrollable.columnconfigure(0, weight=1)

        if not projects:
            ttk.Label(
                scrollable,
                text="Brak projektow. Uzyj przycisku 'Create New Project', aby zaczac.",
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
            return

        for index, project in enumerate(projects):
            card = ttk.Frame(scrollable, style="Card.TFrame", padding=16)
            card.grid(row=index, column=0, sticky="ew", padx=4, pady=6)
            card.columnconfigure(1, weight=1)

            preview = ttk.Frame(card, width=150, height=95)
            preview.grid(row=0, column=0, rowspan=3, sticky="nsw", padx=(0, 16))
            preview.grid_propagate(False)
            self._render_preview(preview, project.preview_image_path, (150, 95), "Brak podgladu")

            ttk.Label(card, text=project.name, style="SubHeader.TLabel").grid(row=0, column=1, sticky="w")
            ttk.Label(card, text=f"Typ: {project.project_type} | Taski: {project.task_count}").grid(row=1, column=1, sticky="w", pady=(4, 2))
            ttk.Label(
                card,
                text=f"Obrazy: {project.image_count} | Adnotacje: {project.annotation_count} | Ostatnia zmiana: {project.updated_at}",
            ).grid(row=2, column=1, sticky="w")
            ttk.Button(card, text="Otworz projekt", command=lambda value=project.id: self._open_project(value)).grid(
                row=0, column=2, rowspan=3, sticky="e"
            )

            for widget in (card, preview):
                widget.bind("<Button-1>", lambda _event, value=project.id: self._open_project(value))

    def show_project_page(self, project: ProjectDetails, tasks: list[TaskSummary]) -> None:
        self.selected_project_id = project.id
        frame = self._reset_content()
        frame.rowconfigure(2, weight=1)

        ttk.Button(frame, text="Powrot do Projects", command=self._back_to_projects_callback).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=project.name, style="Header.TLabel").grid(row=1, column=0, sticky="w", pady=(12, 4))
        ttk.Label(frame, text=f"Typ projektu: {project.project_type}").grid(row=2, column=0, sticky="nw")

        toolbar = ttk.Frame(frame)
        toolbar.grid(row=3, column=0, sticky="ew", pady=(16, 16))
        ttk.Button(toolbar, text="Export Dataset", command=self._export_project_callback).pack(side="right", padx=(8, 0))
        ttk.Button(toolbar, text="Create New Task", command=self._create_task_callback).pack(side="right", padx=(8, 0))
        ttk.Button(toolbar, text="Merge Tasks", command=self._merge_tasks_callback).pack(side="right")

        table = ttk.Treeview(frame, columns=("images", "annotations", "updated"), show="headings", height=14)
        table.grid(row=4, column=0, sticky="nsew")
        table.heading("images", text="Ilosc zdjec")
        table.heading("annotations", text="Ilosc annotacji")
        table.heading("updated", text="Ostatnia zmiana")
        table.column("images", width=140, anchor="center")
        table.column("annotations", width=140, anchor="center")
        table.column("updated", width=220, anchor="center")

        task_map: dict[str, int] = {}
        for task in tasks:
            row_id = table.insert("", "end", values=(task.image_count, task.annotation_count, task.updated_at), text=task.name)
            table.item(row_id, tags=(task.name,))
            task_map[row_id] = task.id
        if not tasks:
            table.insert("", "end", values=("-", "-", "Brak taskow"))

        table.bind("<Double-1>", lambda _event: self._open_selected_task(table, task_map))

        name_column = ttk.Treeview(frame, columns=("name",), show="headings", height=14)
        name_column.grid_remove()

    def show_task_page(self, workspace: dict, image_index: int) -> None:
        project = workspace["project"]
        task = workspace["task"]
        label_templates = workspace["labels"]
        images = workspace["images"]
        annotations_by_image = workspace["annotations"]

        frame = self._reset_content()
        frame.rowconfigure(2, weight=1)
        frame.columnconfigure(1, weight=1)

        toolbar = ttk.Frame(frame)
        toolbar.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        ttk.Button(toolbar, text="Powrot do projektu", command=lambda: self._open_project(project.id)).pack(side="left")
        ttk.Button(toolbar, text="Usun zdjecie z datasetu", command=self._delete_image_callback).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Dodaj label przy uzyciu modelu", command=self._auto_label_callback).pack(side="right")

        counter_text = "0/0"
        current_image = None
        current_annotations = []
        if images:
            current_image = images[image_index]
            current_annotations = annotations_by_image.get(current_image.id, [])
            counter_text = f"{image_index + 1}/{len(images)}"

        ttk.Label(frame, text=f"{project.name} / {task.name}", style="Header.TLabel").grid(row=1, column=0, columnspan=3, sticky="w")
        ttk.Label(frame, text=counter_text).grid(row=1, column=2, sticky="e")

        left_panel = ttk.Frame(frame, padding=(0, 8, 16, 0))
        left_panel.grid(row=2, column=0, sticky="nsw")
        ttk.Label(left_panel, text="Dodaj label", style="SubHeader.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.task_label_var = tk.StringVar(value=str(label_templates[0].id) if label_templates else "")
        label_values = [f"{item.id}|{item.name} [{item.label_type}]" for item in label_templates]
        label_combo = ttk.Combobox(left_panel, values=label_values, state="readonly", width=28)
        if label_values:
            label_combo.set(label_values[0])
        label_combo.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        note_entry = ttk.Entry(left_panel, width=30)
        note_entry.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        note_entry.insert(0, "Krotka notatka do labela")
        ttk.Button(
            left_panel,
            text="Dodaj label",
            command=lambda: self._submit_annotation(label_combo.get(), note_entry.get()),
        ).grid(row=3, column=0, sticky="ew")

        center_panel = ttk.Frame(frame, padding=12)
        center_panel.grid(row=2, column=1, sticky="nsew")
        center_panel.columnconfigure(1, weight=1)
        center_panel.rowconfigure(1, weight=1)

        image_name = Path(current_image.file_path).name if current_image else "Brak obrazu"
        ttk.Label(center_panel, text=image_name, style="SubHeader.TLabel").grid(row=0, column=1, sticky="n")

        image_holder = ttk.Frame(center_panel, style="Card.TFrame", padding=12)
        image_holder.grid(row=1, column=1, sticky="nsew", padx=12, pady=12)
        image_holder.columnconfigure(0, weight=1)
        image_holder.rowconfigure(0, weight=1)
        self._render_preview(image_holder, current_image.file_path if current_image else None, (720, 480), "Brak zdjecia")

        ttk.Button(center_panel, text="Poprzednie", command=lambda: self._change_image(-1)).grid(row=1, column=0, sticky="w")
        ttk.Button(center_panel, text="Nastepne", command=lambda: self._change_image(1)).grid(row=1, column=2, sticky="e")

        right_panel = ttk.Frame(frame, padding=(16, 8, 0, 0))
        right_panel.grid(row=2, column=2, sticky="nse")
        ttk.Label(right_panel, text="Widoczne label'e", style="SubHeader.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))

        tree = ttk.Treeview(right_panel, columns=("type", "source", "visible"), show="headings", height=14)
        tree.grid(row=1, column=0, sticky="nsew")
        tree.heading("type", text="Typ")
        tree.heading("source", text="Zrodlo")
        tree.heading("visible", text="Widoczny")
        tree.column("type", width=140, anchor="center")
        tree.column("source", width=100, anchor="center")
        tree.column("visible", width=90, anchor="center")

        self.annotation_ids_by_row = {}
        for annotation in current_annotations:
            row_id = tree.insert(
                "",
                "end",
                values=(annotation.label_type, annotation.source, "tak" if annotation.is_visible else "nie"),
                text=annotation.label_name,
            )
            self.annotation_ids_by_row[row_id] = annotation.id

        button_row = ttk.Frame(right_panel)
        button_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(button_row, text="Ukryj/Pokaz", command=lambda: self._toggle_selected_annotation(tree)).pack(side="left")
        ttk.Button(button_row, text="Usun label", command=lambda: self._delete_selected_annotation(tree)).pack(side="left", padx=(8, 0))

    def show_settings_page(self, description: str) -> None:
        frame = self._reset_content()
        ttk.Label(frame, text="Settings", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=description, justify="left", wraplength=820).grid(row=1, column=0, sticky="nw", pady=(16, 0))

    def show_info_page(self, description: str) -> None:
        frame = self._reset_content()
        ttk.Label(frame, text="Info", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=description, justify="left", wraplength=820).grid(row=1, column=0, sticky="nw", pady=(16, 0))

    def _open_selected_task(self, table: ttk.Treeview, task_map: dict[str, int]) -> None:
        selected = table.selection()
        if not selected:
            return
        task_id = task_map.get(selected[0])
        if task_id and self._open_task_callback:
            self._open_task_callback(task_id)

    def _submit_annotation(self, combo_value: str, note: str) -> None:
        if not combo_value or not self._add_annotation_callback:
            return
        label_id = int(combo_value.split("|", maxsplit=1)[0])
        self._add_annotation_callback(label_id, note.strip())

    def _toggle_selected_annotation(self, tree: ttk.Treeview) -> None:
        if not self._toggle_annotation_callback:
            return
        selected = tree.selection()
        if not selected:
            return
        annotation_id = self.annotation_ids_by_row.get(selected[0])
        if annotation_id is not None:
            self._toggle_annotation_callback(annotation_id)

    def _delete_selected_annotation(self, tree: ttk.Treeview) -> None:
        if not self._delete_annotation_callback:
            return
        selected = tree.selection()
        if not selected:
            return
        annotation_id = self.annotation_ids_by_row.get(selected[0])
        if annotation_id is not None:
            self._delete_annotation_callback(annotation_id)

    def _open_project(self, project_id: int) -> None:
        self.selected_project_id = project_id
        if self._open_project_callback:
            self._open_project_callback(project_id)

    def _change_image(self, step: int) -> None:
        if self._change_image_callback:
            self._change_image_callback(step)

    def _reset_content(self) -> ttk.Frame:
        for widget in self.content.winfo_children():
            widget.destroy()
        frame = ttk.Frame(self.content)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        return frame

    def _render_preview(self, parent: ttk.Frame, image_path: str | None, size: tuple[int, int], fallback_text: str) -> None:
        for child in parent.winfo_children():
            child.destroy()

        if image_path and Path(image_path).exists() and Image is not None and ImageTk is not None and ImageOps is not None:
            image = Image.open(image_path)
            image = ImageOps.contain(image, size)
            photo = ImageTk.PhotoImage(image)
            self._image_cache = photo
            label = ttk.Label(parent, image=photo)
            label.grid(row=0, column=0, sticky="nsew")
            return

        ttk.Label(parent, text=fallback_text, anchor="center", justify="center").grid(row=0, column=0, sticky="nsew")