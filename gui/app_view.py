from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk

from model.entities import AnnotationRecord, LabelTemplate, ProjectDetails, ProjectSummary, SessionState, TaskSummary

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
        self._delete_project_callback = None
        self._delete_task_callback = None
        self._merge_projects_callback = None
        self._merge_tasks_callback = None
        self._add_annotation_callback = None
        self._update_annotation_callback = None
        self._toggle_annotation_callback = None
        self._delete_annotation_callback = None
        self._delete_image_callback = None
        self._auto_label_callback = None
        self._run_last_model_callback = None
        self._copy_previous_annotation_callback = None
        self._change_image_callback = None

        self.selected_project_id: int | None = None
        self.selected_task_id: int | None = None
        self.annotation_ids_by_row: dict[str, int] = {}
        self.current_task_annotation_labels: dict[str, int] = {}
        self._task_annotations_by_id: dict[int, AnnotationRecord] = {}
        self._image_cache = None
        self._projects_page_cache: list[ProjectSummary] = []
        self._project_page_project: ProjectDetails | None = None
        self._project_page_tasks: list[TaskSummary] = []
        self._task_label_templates_by_id: dict[int, LabelTemplate] = {}
        self._task_label_values: list[str] = []
        self._task_current_annotations: list[AnnotationRecord] = []
        self._task_current_image_path: str | None = None
        self._task_current_draft_points: list[dict[str, float]] = []
        self._task_image_render_box: tuple[float, float, float, float] | None = None
        self._task_image_photo = None
        self._task_image_zoom = 1.0
        self._task_pending_canvas_focus: tuple[float, float, float, float] | None = None
        self._task_zoom_var: tk.StringVar | None = None
        self._task_selected_label_value: str | None = None
        self._task_selected_annotation_id: int | None = None
        self._task_editing_annotation_id: int | None = None
        self._task_selected_draft_point_index: int | None = None
        self._task_dragging_draft_point = False
        self._task_status_var: tk.StringVar | None = None
        self._task_template_info_var: tk.StringVar | None = None
        self._task_template_preview_holder: ttk.Frame | None = None
        self._task_annotation_canvas: tk.Canvas | None = None
        self._task_annotation_image_item: int | None = None
        self._task_submit_button: ttk.Button | None = None

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
        style.configure("SelectedCard.TFrame", background="#e0f2fe", relief="solid", borderwidth=2)
        style.configure("Preview.TFrame", background="#f8fafc", relief="flat", borderwidth=0)
        style.configure("SelectedPreview.TFrame", background="#e0f2fe", relief="flat", borderwidth=0)
        style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("SubHeader.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("CardTitle.TLabel", background="#f8fafc", font=("Segoe UI", 11, "bold"))
        style.configure("CardBody.TLabel", background="#f8fafc")
        style.configure("CardMuted.TLabel", background="#f8fafc", foreground="#475569")
        style.configure("SelectedCardTitle.TLabel", background="#e0f2fe", font=("Segoe UI", 11, "bold"))
        style.configure("SelectedCardBody.TLabel", background="#e0f2fe")
        style.configure("SelectedCardMuted.TLabel", background="#e0f2fe", foreground="#0f172a")

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

    def set_delete_project_callback(self, callback) -> None:
        self._delete_project_callback = callback

    def set_delete_task_callback(self, callback) -> None:
        self._delete_task_callback = callback

    def set_merge_projects_callback(self, callback) -> None:
        self._merge_projects_callback = callback

    def set_merge_tasks_callback(self, callback) -> None:
        self._merge_tasks_callback = callback

    def set_add_annotation_callback(self, callback) -> None:
        self._add_annotation_callback = callback

    def set_update_annotation_callback(self, callback) -> None:
        self._update_annotation_callback = callback

    def set_toggle_annotation_callback(self, callback) -> None:
        self._toggle_annotation_callback = callback

    def set_delete_annotation_callback(self, callback) -> None:
        self._delete_annotation_callback = callback

    def set_delete_image_callback(self, callback) -> None:
        self._delete_image_callback = callback

    def set_auto_label_callback(self, callback) -> None:
        self._auto_label_callback = callback

    def set_run_last_model_callback(self, callback) -> None:
        self._run_last_model_callback = callback

    def set_copy_previous_annotation_callback(self, callback) -> None:
        self._copy_previous_annotation_callback = callback

    def set_change_image_callback(self, callback) -> None:
        self._change_image_callback = callback

    def set_close_callback(self, callback) -> None:
        self.protocol("WM_DELETE_WINDOW", callback)

    def get_selected_project_id(self) -> int | None:
        return self.selected_project_id

    def get_selected_task_id(self) -> int | None:
        return self.selected_task_id

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
        self._projects_page_cache = list(projects)
        available_ids = {project.id for project in projects}
        if self.selected_project_id not in available_ids:
            self.selected_project_id = None

        frame = self._reset_content()
        frame.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 16))

        ttk.Label(toolbar, text="Projects", style="Header.TLabel").pack(side="left")
        ttk.Button(toolbar, text="Create New Project", command=self._create_project_callback).pack(side="right", padx=(8, 0))
        ttk.Button(toolbar, text="Merge Projects", command=self._merge_projects_callback).pack(side="right", padx=(8, 0))
        ttk.Button(toolbar, text="Usun projekt", command=self._delete_project_callback).pack(side="right", padx=(8, 0))
        ttk.Button(toolbar, text="Export Dataset", command=self._export_project_callback).pack(side="right")

        canvas = tk.Canvas(frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        scrollable_window = canvas.create_window((0, 0), window=scrollable, anchor="nw")
        scrollable.bind(
            "<Configure>",
            lambda event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(scrollable_window, width=event.width),
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        scrollable.columnconfigure(0, weight=1)

        if not projects:
            ttk.Label(
                scrollable,
                text="Brak projektow. Uzyj przycisku 'Create New Project', aby zaczac.",
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
            self._bind_mousewheel_scrolling(canvas, canvas)
            return

        for index, project in enumerate(projects):
            selected = project.id == self.selected_project_id
            frame_style, title_style, body_style, muted_style = self._get_card_styles(selected)
            preview_style = self._get_preview_style(selected)

            card = ttk.Frame(scrollable, style=frame_style, padding=16)
            card.grid(row=index, column=0, sticky="ew", padx=4, pady=6)
            card.columnconfigure(1, weight=1)

            preview = ttk.Frame(card, style=preview_style, width=150, height=95)
            preview.grid(row=0, column=0, rowspan=3, sticky="nsw", padx=(0, 16))
            preview.grid_propagate(False)
            self._render_preview(preview, project.preview_image_path, (150, 95), "Brak podgladu")

            title = ttk.Label(card, text=project.name, style=title_style)
            title.grid(row=0, column=1, sticky="w")
            details = ttk.Label(card, text=f"Typ: {project.project_type} | Taski: {project.task_count}", style=body_style)
            details.grid(row=1, column=1, sticky="w", pady=(4, 2))
            stats = ttk.Label(
                card,
                text=f"Obrazy: {project.image_count} | Adnotacje: {project.annotation_count} | Ostatnia zmiana: {project.updated_at}",
                style=muted_style,
            )
            stats.grid(row=2, column=1, sticky="w")
            if project.storage_path:
                location = ttk.Label(card, text=f"Lokalizacja: {project.storage_path}", style=muted_style)
                location.grid(row=3, column=1, sticky="w", pady=(4, 0))
            ttk.Button(card, text="Otworz projekt", command=lambda value=project.id: self._open_project(value)).grid(
                row=0, column=2, rowspan=4, sticky="e"
            )

            self._bind_card_interactions(
                [card],
                lambda _event, value=project.id: self._select_project_card(value),
                lambda _event, value=project.id: self._open_project(value),
            )

        self._bind_mousewheel_scrolling(canvas, canvas)

    def show_project_page(self, project: ProjectDetails, tasks: list[TaskSummary]) -> None:
        self.selected_project_id = project.id
        self._project_page_project = project
        self._project_page_tasks = list(tasks)
        available_ids = {task.id for task in tasks}
        if self.selected_task_id not in available_ids:
            self.selected_task_id = None

        frame = self._reset_content()
        frame.rowconfigure(4, weight=1)

        ttk.Button(frame, text="Powrot do Projects", command=self._back_to_projects_callback).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=project.name, style="Header.TLabel").grid(row=1, column=0, sticky="w", pady=(12, 4))
        ttk.Label(frame, text=f"Typ projektu: {project.project_type}").grid(row=2, column=0, sticky="nw")
        if project.storage_path:
            ttk.Label(frame, text=f"Lokalizacja projektu: {project.storage_path}").grid(row=2, column=0, sticky="ne")

        toolbar = ttk.Frame(frame)
        toolbar.grid(row=3, column=0, sticky="ew", pady=(16, 16))
        ttk.Button(toolbar, text="Export Dataset", command=self._export_project_callback).pack(side="right", padx=(8, 0))
        ttk.Button(toolbar, text="Create New Task", command=self._create_task_callback).pack(side="right", padx=(8, 0))
        ttk.Button(toolbar, text="Usun task", command=self._delete_task_callback).pack(side="right", padx=(8, 0))
        ttk.Button(toolbar, text="Merge Tasks", command=self._merge_tasks_callback).pack(side="right")

        canvas = tk.Canvas(frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        scrollable_window = canvas.create_window((0, 0), window=scrollable, anchor="nw")
        scrollable.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(scrollable_window, width=event.width),
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=4, column=0, sticky="nsew")
        scrollbar.grid(row=4, column=1, sticky="ns")
        scrollable.columnconfigure(0, weight=1)

        for index, task in enumerate(tasks):
            selected = task.id == self.selected_task_id
            frame_style, title_style, body_style, muted_style = self._get_card_styles(selected)
            preview_style = self._get_preview_style(selected)

            card = ttk.Frame(scrollable, style=frame_style, padding=16)
            card.grid(row=index, column=0, sticky="ew", padx=4, pady=6)
            card.columnconfigure(1, weight=1)

            preview = ttk.Frame(card, style=preview_style, width=150, height=95)
            preview.grid(row=0, column=0, rowspan=4, sticky="nsw", padx=(0, 16))
            preview.grid_propagate(False)
            self._render_preview(preview, task.preview_image_path, (150, 95), "Brak podgladu")

            title = ttk.Label(card, text=task.name, style=title_style)
            title.grid(row=0, column=1, sticky="w")
            dataset_text = task.dataset_path or "Brak folderu datasetu"
            dataset = ttk.Label(card, text=f"Dataset: {dataset_text}", style=body_style)
            dataset.grid(row=1, column=1, sticky="w", pady=(4, 2))
            stats = ttk.Label(
                card,
                text=f"Obrazy: {task.image_count} | Adnotacje: {task.annotation_count}",
                style=body_style,
            )
            stats.grid(row=2, column=1, sticky="w")
            updated = ttk.Label(card, text=f"Ostatnia zmiana: {task.updated_at}", style=muted_style)
            updated.grid(row=3, column=1, sticky="w", pady=(4, 0))
            ttk.Button(card, text="Otworz task", command=lambda value=task.id: self._open_task(value)).grid(
                row=0, column=2, rowspan=4, sticky="e"
            )

            self._bind_card_interactions(
                [card],
                lambda _event, value=task.id: self._select_task_card(value),
                lambda _event, value=task.id: self._open_task(value),
            )

        if not tasks:
            ttk.Label(
                scrollable,
                text="Brak taskow. Uzyj przycisku 'Create New Task', aby dodac pierwszy task.",
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)

        self._bind_mousewheel_scrolling(canvas, canvas)

    def show_task_page(self, workspace: dict, image_index: int) -> None:
        project = workspace["project"]
        task = workspace["task"]
        label_templates = workspace["labels"]
        images = workspace["images"]
        annotations_by_image = workspace["annotations"]

        frame = self._reset_content()
        frame.rowconfigure(2, weight=1)
        frame.columnconfigure(0, weight=1)

        toolbar = ttk.Frame(frame)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        ttk.Button(toolbar, text="Powrot do projektu", command=lambda: self._open_project(project.id)).pack(side="left")
        ttk.Button(toolbar, text="Usun zdjecie z datasetu", command=self._delete_image_callback).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Uruchom ostatni model", command=self._run_last_model_callback).pack(side="right")
        ttk.Button(toolbar, text="Dodaj label przy uzyciu modelu", command=self._auto_label_callback).pack(side="right")

        counter_text = "0/0"
        current_image = None
        current_annotations = []
        if images:
            current_image = images[image_index]
            current_annotations = annotations_by_image.get(current_image.id, [])
            counter_text = f"{image_index + 1}/{len(images)}"

        ttk.Label(frame, text=f"{project.name} / {task.name}", style="Header.TLabel").grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text=counter_text).grid(row=1, column=1, sticky="e")

        self._task_label_templates_by_id = {item.id: item for item in label_templates if item.id is not None}
        self._task_current_annotations = current_annotations
        self._task_annotations_by_id = {item.id: item for item in current_annotations}
        self._task_current_image_path = current_image.file_path if current_image else None
        self._task_current_draft_points = []
        available_annotation_ids = set(self._task_annotations_by_id)
        if self._task_selected_annotation_id not in available_annotation_ids:
            self._task_selected_annotation_id = None
        self._task_editing_annotation_id = None
        label_values = [f"{item.id}|{item.name} [{item.label_type}]" for item in label_templates]
        self._task_label_values = label_values
        selected_label_value = self._task_selected_label_value if self._task_selected_label_value in label_values else (label_values[0] if label_values else "")
        self.task_label_var = tk.StringVar(value=selected_label_value)
        self._task_status_var = tk.StringVar(value="Wybierz etykiete, aby annotowac obraz.")
        label_combo = ttk.Combobox(frame, textvariable=self.task_label_var, values=label_values, state="readonly", width=32)
        label_combo.grid(row=2, column=0, sticky="w", pady=(0, 8))
        label_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_task_label_selected(self.task_label_var.get()))
        self._bind_task_navigation_keys()

        center_panel = ttk.Frame(frame, padding=12)
        center_panel.grid(row=3, column=0, sticky="nsew")
        center_panel.columnconfigure(1, weight=1)
        center_panel.rowconfigure(3, weight=1)

        controls = ttk.Frame(center_panel)
        controls.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        ttk.Label(controls, text="Dodaj label", style="SubHeader.TLabel").pack(side="left")
        self._task_zoom_var = tk.StringVar(value="Zoom: 100%")
        zoom_controls = ttk.Frame(controls)
        zoom_controls.pack(side="left", padx=(16, 0))
        ttk.Button(zoom_controls, text="-", width=3, command=lambda: self._change_task_zoom(-0.25)).pack(side="left")
        ttk.Label(zoom_controls, textvariable=self._task_zoom_var).pack(side="left", padx=8)
        ttk.Button(zoom_controls, text="+", width=3, command=lambda: self._change_task_zoom(0.25)).pack(side="left")
        ttk.Button(zoom_controls, text="Reset", command=self._reset_task_zoom).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Cofnij punkt", command=self._undo_task_annotation_point).pack(side="right")
        self._task_submit_button = ttk.Button(
            controls,
            text="Dodaj label",
            command=self._handle_task_annotation_submit,
        )
        self._task_submit_button.pack(side="right", padx=(8, 0))
        ttk.Button(
            controls,
            text="Ukryj/Odkryj keypoint",
            command=self._toggle_selected_task_keypoint_visibility,
        ).pack(side="right", padx=(8, 0))
        ttk.Button(
            controls,
            text="Skopiuj z poprzedniego zdjecia",
            command=self._copy_task_annotation_from_previous_image,
        ).pack(side="right", padx=(8, 0))
        ttk.Button(controls, text="Wyczysc szkic", command=self._clear_task_annotation_draft).pack(side="right", padx=(8, 0))
        ttk.Label(center_panel, textvariable=self._task_status_var, justify="left", wraplength=860).grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=(0, 8)
        )

        image_name = Path(current_image.file_path).name if current_image else "Brak obrazu"
        ttk.Label(center_panel, text=image_name, style="SubHeader.TLabel").grid(row=2, column=1, sticky="n")

        image_holder = ttk.Frame(center_panel, style="Card.TFrame", padding=12)
        image_holder.grid(row=3, column=1, sticky="nsew", padx=12, pady=12)
        image_holder.columnconfigure(0, weight=1)
        image_holder.rowconfigure(0, weight=1)
        task_canvas_scroll_y = ttk.Scrollbar(image_holder, orient="vertical")
        task_canvas_scroll_x = ttk.Scrollbar(image_holder, orient="horizontal")
        self._task_annotation_canvas = tk.Canvas(
            image_holder,
            width=720,
            height=480,
            background="#0f172a",
            highlightthickness=0,
            cursor="crosshair",
            xscrollcommand=task_canvas_scroll_x.set,
            yscrollcommand=task_canvas_scroll_y.set,
        )
        self._task_annotation_canvas.grid(row=0, column=0, sticky="nsew")
        task_canvas_scroll_y.config(command=self._task_annotation_canvas.yview)
        task_canvas_scroll_x.config(command=self._task_annotation_canvas.xview)
        task_canvas_scroll_y.grid(row=0, column=1, sticky="ns")
        task_canvas_scroll_x.grid(row=1, column=0, sticky="ew")
        self._task_annotation_canvas.bind("<ButtonPress-1>", self._on_task_image_press)
        self._task_annotation_canvas.bind("<B1-Motion>", self._on_task_image_drag)
        self._task_annotation_canvas.bind("<ButtonRelease-1>", self._on_task_image_release)
        self._task_annotation_canvas.bind("<MouseWheel>", self._on_task_annotation_mousewheel)
        self._task_annotation_canvas.bind("<Button-4>", self._on_task_annotation_mousewheel)
        self._task_annotation_canvas.bind("<Button-5>", self._on_task_annotation_mousewheel)
        self._render_task_annotation_canvas()

        if label_values:
            self._on_task_label_selected(self.task_label_var.get())

        ttk.Button(center_panel, text="Poprzednie", command=lambda: self._change_image(-1)).grid(row=3, column=0, sticky="w")
        ttk.Button(center_panel, text="Nastepne", command=lambda: self._change_image(1)).grid(row=3, column=2, sticky="e")

        right_panel = ttk.Frame(frame, padding=(16, 8, 0, 0))
        right_panel.grid(row=3, column=1, sticky="nse")
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
        selected_row_id: str | None = None
        for annotation in current_annotations:
            row_id = tree.insert(
                "",
                "end",
                values=(annotation.label_type, annotation.source, "tak" if annotation.is_visible else "nie"),
                text=annotation.label_name,
            )
            self.annotation_ids_by_row[row_id] = annotation.id
            if annotation.id == self._task_selected_annotation_id:
                selected_row_id = row_id

        tree.bind("<<TreeviewSelect>>", lambda _event: self._on_task_annotation_tree_selected(tree))
        if selected_row_id is not None:
            tree.selection_set(selected_row_id)

        button_row = ttk.Frame(right_panel)
        button_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(button_row, text="Zmien polozenie keypointow", command=lambda: self._start_selected_annotation_reposition(tree)).pack(side="left")
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

    def _get_card_styles(self, selected: bool) -> tuple[str, str, str, str]:
        if selected:
            return ("SelectedCard.TFrame", "SelectedCardTitle.TLabel", "SelectedCardBody.TLabel", "SelectedCardMuted.TLabel")
        return ("Card.TFrame", "CardTitle.TLabel", "CardBody.TLabel", "CardMuted.TLabel")

    def _get_preview_style(self, selected: bool) -> str:
        if selected:
            return "SelectedPreview.TFrame"
        return "Preview.TFrame"

    def _bind_card_interactions(self, widgets: list[tk.Widget], single_click, double_click) -> None:
        for widget in widgets:
            widget.bind("<Button-1>", single_click)
            widget.bind("<Double-1>", double_click)
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button):
                    continue
                self._bind_card_interactions([child], single_click, double_click)

    def _bind_mousewheel_scrolling(self, canvas: tk.Canvas, root: tk.Widget) -> None:
        root.bind("<MouseWheel>", lambda event: self._on_mousewheel_scroll(canvas, event), add="+")
        root.bind("<Button-4>", lambda event: self._on_mousewheel_scroll(canvas, event), add="+")
        root.bind("<Button-5>", lambda event: self._on_mousewheel_scroll(canvas, event), add="+")
        for child in root.winfo_children():
            self._bind_mousewheel_scrolling(canvas, child)

    def _on_mousewheel_scroll(self, canvas: tk.Canvas, event: tk.Event) -> str:
        if getattr(event, "delta", 0):
            step = -int(event.delta / 120)
        elif getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            step = 0

        if step != 0:
            scroll_region = canvas.bbox("all")
            if not scroll_region:
                return "break"

            content_height = scroll_region[3] - scroll_region[1]
            viewport_height = canvas.winfo_height()
            if content_height <= viewport_height:
                canvas.yview_moveto(0)
                return "break"

            start, end = canvas.yview()
            if (step < 0 and start <= 0.0) or (step > 0 and end >= 1.0):
                return "break"

            canvas.yview_scroll(step, "units")
        return "break"

    def _select_project_card(self, project_id: int) -> None:
        if self.selected_project_id == project_id:
            return
        self.selected_project_id = project_id
        self.show_projects_page(self._projects_page_cache)

    def _select_task_card(self, task_id: int) -> None:
        if self._project_page_project is None:
            return
        if self.selected_task_id == task_id:
            return
        self.selected_task_id = task_id
        self.show_project_page(self._project_page_project, self._project_page_tasks)

    def _submit_annotation(
        self,
        combo_value: str,
        note: str,
        annotation_definition: dict[str, object] | None = None,
    ) -> None:
        if not combo_value or not self._add_annotation_callback:
            return
        label_id = int(combo_value.split("|", maxsplit=1)[0])
        self._add_annotation_callback(label_id, note.strip(), annotation_definition)

    def _handle_task_annotation_submit(self) -> None:
        annotation_definition = self._build_task_annotation_definition()
        if self._task_editing_annotation_id is not None:
            if self._update_annotation_callback is not None and annotation_definition is not None:
                self._update_annotation_callback(self._task_editing_annotation_id, annotation_definition)
            return
        combo_value = self.task_label_var.get() if hasattr(self, "task_label_var") else ""
        self._submit_annotation(combo_value, "", annotation_definition)

    def _copy_task_annotation_from_previous_image(self) -> None:
        if self._copy_previous_annotation_callback is None:
            return
        combo_value = self.task_label_var.get() if hasattr(self, "task_label_var") else ""
        self._copy_previous_annotation_callback(combo_value)

    def _refresh_task_submit_button(self) -> None:
        if self._task_submit_button is None:
            return
        button_text = "Zapisz polozenie keypointow" if self._task_editing_annotation_id is not None else "Dodaj label"
        self._task_submit_button.configure(text=button_text)

    def _on_task_label_selected(self, combo_value: str) -> None:
        self._task_selected_label_value = combo_value or None
        label_id = self._resolve_task_label_id(combo_value)
        label_template = self._task_label_templates_by_id.get(label_id)
        self._task_current_draft_points = []
        self._task_editing_annotation_id = None
        self._task_selected_draft_point_index = None
        self._task_dragging_draft_point = False
        self._refresh_task_submit_button()
        self._render_task_annotation_overlay()
        if label_template is None:
            if self._task_status_var is not None:
                self._task_status_var.set("Wybierz etykietę, aby annotować obraz.")
            return

        if self._task_status_var is not None:
            self._task_status_var.set(self._describe_task_draft_state(label_template, label_template.preview_definition))

    def _resolve_task_label_id(self, combo_value: str) -> int | None:
        if not combo_value:
            return None
        try:
            return int(combo_value.split("|", maxsplit=1)[0])
        except (TypeError, ValueError):
            return None

    def _describe_task_label_template(self, label_template: LabelTemplate) -> str:
        template_definition = label_template.preview_definition
        if template_definition is None:
            return f"Typ: {label_template.label_type}. Ta etykieta nie ma zapisanego szkicu wzorcowego."
        points = template_definition.get("points", [])
        point_count = len(points) if isinstance(points, list) else 0
        return f"Typ: {label_template.label_type}. Zapisany wzorzec: {point_count} pkt. Uzyj go na aktualnym obrazie."

    def _describe_task_draft_state(
        self,
        label_template: LabelTemplate,
        template_definition: dict[str, object] | None,
    ) -> str:
        if label_template.label_type == "Klasyfikacja":
            return "Klasyfikacja nie wymaga szkicu na obrazie."
        target_points = 0
        if isinstance(template_definition, dict):
            points = template_definition.get("points", [])
            target_points = len(points) if isinstance(points, list) else 0
        current_points = len(self._task_current_draft_points)
        visible_points = sum(1 for point in self._task_current_draft_points if self._get_task_point_visibility(point) > 0)
        if label_template.label_type == "Bounding box":
            return f"Kliknij dwa rogi boxa na aktualnym obrazie. Postep: {current_points}/2."
        if label_template.label_type == "Point":
            return f"Kliknij punkt na aktualnym obrazie. Możesz go potem przeciągnąć lub ukryć. Postep: {current_points}/1. Widoczne: {visible_points}."
        if label_template.label_type == "Skeleton":
            return f"Klikaj kolejne punkty skeletonu. Dodane punkty możesz zaznaczyć, przeciągać i ukrywać. Postep: {current_points}/{target_points or '?'} . Widoczne: {visible_points}."
        if label_template.label_type == "Polyline":
            return f"Klikaj kolejne punkty linii. Postep: {current_points}/{target_points or 'wiele'} ."
        if label_template.label_type in {"Polygon", "Segmentacja (maska)"}:
            return f"Klikaj wierzcholki obrysu. Postep: {current_points}/{target_points or 'wiele'} ."
        return "Rysuj szkic na aktualnym obrazie zgodnie z zapisanym wzorcem."

    def _find_task_draft_point_index(self, canvas_x: float, canvas_y: float, radius: float = 10.0) -> int | None:
        if not self._task_current_draft_points:
            return None
        best_index: int | None = None
        best_distance = radius * radius
        for index, point in enumerate(self._task_current_draft_points):
            if not isinstance(point, dict) or "x" not in point or "y" not in point:
                continue
            point_x, point_y = self._to_task_canvas_point(point)
            distance = (point_x - canvas_x) ** 2 + (point_y - canvas_y) ** 2
            if distance <= best_distance:
                best_distance = distance
                best_index = index
        return best_index

    def _get_task_point_visibility(self, point: dict[str, float]) -> int:
        raw_visibility = point.get("visibility", 2)
        try:
            return 0 if int(raw_visibility) <= 0 else 2
        except (TypeError, ValueError):
            return 2

    def _clone_task_point(self, point: dict[str, float], *, visibility: int | None = None) -> dict[str, float]:
        cloned_point = {
            "x": float(point["x"]),
            "y": float(point["y"]),
        }
        point_visibility = self._get_task_point_visibility(point) if visibility is None else visibility
        if point_visibility <= 0:
            cloned_point["visibility"] = 0
        return cloned_point

    def _get_task_canvas_event_coords(self, event: tk.Event) -> tuple[float, float]:
        if self._task_annotation_canvas is None:
            return float(event.x), float(event.y)
        return (
            float(self._task_annotation_canvas.canvasx(event.x)),
            float(self._task_annotation_canvas.canvasy(event.y)),
        )

    def _get_task_canvas_focus(
        self,
        viewport_x: float | None = None,
        viewport_y: float | None = None,
    ) -> tuple[float, float, float, float] | None:
        if self._task_annotation_canvas is None or self._task_image_render_box is None:
            return None

        canvas = self._task_annotation_canvas
        viewport_width = max(1.0, float(canvas.winfo_width()))
        viewport_height = max(1.0, float(canvas.winfo_height()))
        anchor_viewport_x = float(viewport_x) if viewport_x is not None else viewport_width / 2
        anchor_viewport_y = float(viewport_y) if viewport_y is not None else viewport_height / 2
        anchor_canvas_x = float(canvas.canvasx(anchor_viewport_x))
        anchor_canvas_y = float(canvas.canvasy(anchor_viewport_y))
        x0, y0, x1, y1 = self._task_image_render_box
        image_width = max(1.0, x1 - x0)
        image_height = max(1.0, y1 - y0)
        relative_x = min(1.0, max(0.0, (anchor_canvas_x - x0) / image_width))
        relative_y = min(1.0, max(0.0, (anchor_canvas_y - y0) / image_height))
        return (relative_x, relative_y, anchor_viewport_x, anchor_viewport_y)

    def _restore_task_canvas_focus(self, focus: tuple[float, float, float, float] | None) -> None:
        if self._task_annotation_canvas is None or self._task_image_render_box is None or focus is None:
            return

        canvas = self._task_annotation_canvas
        canvas.update_idletasks()
        scroll_region = canvas.cget("scrollregion")
        if not isinstance(scroll_region, str):
            return
        parts = scroll_region.split()
        if len(parts) != 4:
            return

        region_left, region_top, region_right, region_bottom = [float(value) for value in parts]
        region_width = max(1.0, region_right - region_left)
        region_height = max(1.0, region_bottom - region_top)
        viewport_width = max(1.0, float(canvas.winfo_width()))
        viewport_height = max(1.0, float(canvas.winfo_height()))
        x0, y0, x1, y1 = self._task_image_render_box
        image_width = max(1.0, x1 - x0)
        image_height = max(1.0, y1 - y0)
        target_anchor_x = x0 + focus[0] * image_width
        target_anchor_y = y0 + focus[1] * image_height
        anchor_viewport_x = min(viewport_width, max(0.0, focus[2]))
        anchor_viewport_y = min(viewport_height, max(0.0, focus[3]))

        if region_width <= viewport_width:
            canvas.xview_moveto(0)
        else:
            x_fraction = (target_anchor_x - anchor_viewport_x - region_left) / max(1.0, region_width - viewport_width)
            canvas.xview_moveto(min(1.0, max(0.0, x_fraction)))

        if region_height <= viewport_height:
            canvas.yview_moveto(0)
        else:
            y_fraction = (target_anchor_y - anchor_viewport_y - region_top) / max(1.0, region_height - viewport_height)
            canvas.yview_moveto(min(1.0, max(0.0, y_fraction)))

    def _change_task_zoom(self, delta: float, focus: tuple[float, float, float, float] | None = None) -> None:
        new_zoom = min(6.0, max(1.0, round(self._task_image_zoom + delta, 2)))
        if abs(new_zoom - self._task_image_zoom) < 1e-9:
            return
        self._task_pending_canvas_focus = focus or self._get_task_canvas_focus() or (0.5, 0.5, 360.0, 240.0)
        self._task_image_zoom = new_zoom
        if self._task_zoom_var is not None:
            self._task_zoom_var.set(f"Zoom: {round(self._task_image_zoom * 100):d}%")
        self._render_task_annotation_canvas()

    def _reset_task_zoom(self) -> None:
        self._task_pending_canvas_focus = (0.5, 0.5, 360.0, 240.0)
        self._task_image_zoom = 1.0
        if self._task_zoom_var is not None:
            self._task_zoom_var.set("Zoom: 100%")
        self._render_task_annotation_canvas()

    def _on_task_annotation_mousewheel(self, event: tk.Event) -> str:
        if self._task_annotation_canvas is None:
            return "break"
        delta = 0
        if hasattr(event, "delta") and event.delta:
            delta = 1 if event.delta > 0 else -1
        elif getattr(event, "num", None) == 4:
            delta = 1
        elif getattr(event, "num", None) == 5:
            delta = -1
        if delta == 0:
            return "break"

        if getattr(event, "state", 0) & 0x0004:
            self._change_task_zoom(
                0.25 if delta > 0 else -0.25,
                focus=self._get_task_canvas_focus(float(event.x), float(event.y)),
            )
            return "break"

        self._task_annotation_canvas.yview_scroll(-delta, "units")
        return "break"

    def _on_task_image_press(self, event: tk.Event) -> None:
        canvas_x, canvas_y = self._get_task_canvas_event_coords(event)
        point_index = self._find_task_draft_point_index(canvas_x, canvas_y)
        if point_index is not None:
            self._task_selected_draft_point_index = point_index
            self._task_dragging_draft_point = False
            self._render_task_annotation_overlay()
            return
        self._task_selected_draft_point_index = None
        self._task_dragging_draft_point = False
        self._on_task_image_click(event)

    def _on_task_image_click(self, event: tk.Event) -> None:
        label_id = self._resolve_task_label_id(self.task_label_var.get() if hasattr(self, "task_label_var") else "")
        label_template = self._task_label_templates_by_id.get(label_id)
        if label_template is None:
            return

        if self._task_editing_annotation_id is not None:
            if self._task_status_var is not None:
                self._task_status_var.set("W trybie zmiany polozenia przeciagaj istniejace punkty, zamiast dodawac nowe.")
            return

        canvas_x, canvas_y = self._get_task_canvas_event_coords(event)
        point = self._to_task_normalized_point(canvas_x, canvas_y)
        if point is None:
            return
        if label_template.label_type == "Klasyfikacja":
            if self._task_status_var is not None:
                self._task_status_var.set("Klasyfikacja nie wymaga klikania na obrazie.")
            return

        template_points = []
        if label_template.preview_definition is not None:
            points = label_template.preview_definition.get("points", [])
            if isinstance(points, list):
                template_points = points

        if label_template.label_type == "Point":
            self._task_current_draft_points = [self._clone_task_point(point)]
        elif label_template.label_type == "Bounding box":
            if len(self._task_current_draft_points) >= 2:
                self._task_current_draft_points = [self._clone_task_point(point)]
            else:
                self._task_current_draft_points.append(self._clone_task_point(point))
        else:
            if label_template.label_type == "Skeleton" and template_points and len(self._task_current_draft_points) >= len(template_points):
                if self._task_status_var is not None:
                    self._task_status_var.set("Skeleton ma juz komplet punktow. Uzyj cofania albo wyczysc szkic.")
                return
            self._task_current_draft_points.append(self._clone_task_point(point))

        self._render_task_annotation_overlay()
        if self._task_status_var is not None:
            self._task_status_var.set(self._describe_task_draft_state(label_template, label_template.preview_definition))

        if self._is_task_annotation_complete(label_template) and label_template.label_type not in {"Point", "Skeleton"}:
            self._submit_annotation(
                self.task_label_var.get() if hasattr(self, "task_label_var") else "",
                "",
                self._build_task_annotation_definition(),
            )

    def _on_task_image_drag(self, event: tk.Event) -> None:
        point_index = self._task_selected_draft_point_index
        if point_index is None:
            return
        if point_index < 0 or point_index >= len(self._task_current_draft_points):
            self._task_selected_draft_point_index = None
            return

        canvas_x, canvas_y = self._get_task_canvas_event_coords(event)
        point = self._to_task_normalized_point(canvas_x, canvas_y)
        if point is None:
            return

        current_point = self._task_current_draft_points[point_index]
        self._task_current_draft_points[point_index] = self._clone_task_point(point, visibility=self._get_task_point_visibility(current_point))
        self._task_dragging_draft_point = True
        self._render_task_annotation_overlay()

    def _on_task_image_release(self, _event: tk.Event) -> None:
        if self._task_selected_draft_point_index is None:
            return
        self._task_dragging_draft_point = False
        self._render_task_annotation_overlay()

    def _undo_task_annotation_point(self) -> None:
        if not self._task_current_draft_points:
            return
        self._task_current_draft_points.pop()
        self._task_selected_draft_point_index = None
        self._task_dragging_draft_point = False
        self._render_task_annotation_overlay()
        label_id = self._resolve_task_label_id(self.task_label_var.get() if hasattr(self, "task_label_var") else "")
        label_template = self._task_label_templates_by_id.get(label_id)
        if label_template is not None and self._task_status_var is not None:
            self._task_status_var.set(self._describe_task_draft_state(label_template, label_template.preview_definition))

    def _clear_task_annotation_draft(self) -> None:
        self._task_current_draft_points = []
        self._task_editing_annotation_id = None
        self._task_selected_draft_point_index = None
        self._task_dragging_draft_point = False
        self._refresh_task_submit_button()
        self._render_task_annotation_overlay()
        label_id = self._resolve_task_label_id(self.task_label_var.get() if hasattr(self, "task_label_var") else "")
        label_template = self._task_label_templates_by_id.get(label_id)
        if label_template is not None and self._task_status_var is not None:
            self._task_status_var.set(self._describe_task_draft_state(label_template, label_template.preview_definition))

    def _build_task_annotation_definition(self) -> dict[str, object] | None:
        label_id = self._resolve_task_label_id(self.task_label_var.get() if hasattr(self, "task_label_var") else "")
        label_template = self._task_label_templates_by_id.get(label_id)
        if label_template is None or label_template.label_type == "Klasyfikacja":
            return None
        if not self._task_current_draft_points:
            return None

        payload: dict[str, object] = {
            "type": label_template.label_type,
            "points": [self._clone_task_point(point) for point in self._task_current_draft_points],
        }
        if label_template.preview_definition is not None and label_template.label_type == "Skeleton":
            template_points = label_template.preview_definition.get("points", [])
            if isinstance(template_points, list):
                payload["point_count"] = len(template_points)
        return payload

    def _is_task_annotation_complete(self, label_template: LabelTemplate) -> bool:
        current_points = len(self._task_current_draft_points)
        if label_template.label_type == "Point":
            return current_points == 1
        if label_template.label_type == "Bounding box":
            return current_points == 2

        template_definition = label_template.preview_definition or {}
        template_points = template_definition.get("points", []) if isinstance(template_definition, dict) else []
        expected_count = len(template_points) if isinstance(template_points, list) else 0

        if label_template.label_type == "Skeleton":
            return expected_count > 0 and current_points == expected_count
        if label_template.label_type == "Polyline":
            return expected_count >= 2 and current_points >= expected_count
        if label_template.label_type in {"Polygon", "Segmentacja (maska)"}:
            return expected_count >= 3 and current_points >= expected_count
        return False

    def _to_task_normalized_point(self, canvas_x: float, canvas_y: float) -> dict[str, float] | None:
        if self._task_image_render_box is None:
            return None
        x0, y0, x1, y1 = self._task_image_render_box
        if canvas_x < x0 or canvas_x > x1 or canvas_y < y0 or canvas_y > y1:
            return None
        width = max(1.0, x1 - x0)
        height = max(1.0, y1 - y0)
        return {
            "x": round((canvas_x - x0) / width, 4),
            "y": round((canvas_y - y0) / height, 4),
        }

    def _to_task_canvas_point(self, point: dict[str, float]) -> tuple[float, float]:
        x0, y0, x1, y1 = self._task_image_render_box or (0.0, 0.0, 1.0, 1.0)
        return (x0 + point["x"] * (x1 - x0), y0 + point["y"] * (y1 - y0))

    def _render_task_annotation_overlay(self) -> None:
        if self._task_annotation_canvas is None:
            return
        canvas = self._task_annotation_canvas
        canvas.delete("annotation_overlay")

        if self._task_image_render_box is None:
            return

        for annotation in reversed(self._task_current_annotations):
            if annotation.annotation_definition is None:
                continue
            if annotation.id == self._task_selected_annotation_id:
                continue
            self._draw_task_annotation_shape(annotation.annotation_definition, "#38bdf8")

        selected_annotation = self._task_annotations_by_id.get(self._task_selected_annotation_id) if self._task_selected_annotation_id is not None else None
        if selected_annotation is not None and selected_annotation.annotation_definition is not None:
            if selected_annotation.id != self._task_editing_annotation_id:
                self._draw_task_annotation_shape(
                    selected_annotation.annotation_definition,
                    "#f59e0b",
                    show_indexes=selected_annotation.label_type in {"Point", "Skeleton"},
                )

        draft_definition = self._build_task_annotation_definition()
        if draft_definition is not None:
            self._draw_task_annotation_shape(
                draft_definition,
                "#ef4444",
                show_indexes=True,
                selected_point_index=self._task_selected_draft_point_index,
            )

    def _render_task_annotation_canvas(self) -> None:
        if self._task_annotation_canvas is None:
            return
        canvas = self._task_annotation_canvas
        canvas_focus = self._task_pending_canvas_focus
        self._task_pending_canvas_focus = None
        canvas.delete("task_message")
        self._task_image_photo = None
        self._task_image_render_box = None
        canvas.configure(scrollregion=(0, 0, 720, 480))

        image_path = self._task_current_image_path
        if image_path and Path(image_path).exists() and Image is not None and ImageTk is not None and ImageOps is not None:
            image = Image.open(image_path)
            image = ImageOps.contain(
                image,
                (
                    max(1, round(720 * self._task_image_zoom)),
                    max(1, round(480 * self._task_image_zoom)),
                ),
            )
            photo = ImageTk.PhotoImage(image)
            self._task_image_photo = photo
            left = (720 - image.width) / 2
            top = (480 - image.height) / 2
            right = left + image.width
            bottom = top + image.height
            self._task_image_render_box = (left, top, right, bottom)
            canvas.configure(
                scrollregion=(
                    min(0.0, left),
                    min(0.0, top),
                    max(720.0, right),
                    max(480.0, bottom),
                )
            )
            if self._task_annotation_image_item is None:
                self._task_annotation_image_item = canvas.create_image(left, top, image=photo, anchor="nw", tags=("task_image",))
            else:
                canvas.coords(self._task_annotation_image_item, left, top)
                canvas.itemconfigure(self._task_annotation_image_item, image=photo)
            canvas.tag_lower("task_image")
        else:
            canvas.delete("annotation_overlay")
            if self._task_annotation_image_item is not None:
                canvas.delete(self._task_annotation_image_item)
                self._task_annotation_image_item = None
            canvas.create_text(360, 240, text="Brak obrazu do annotacji", fill="#e5e7eb", tags=("task_message",))
            return

        self._render_task_annotation_overlay()
        self._restore_task_canvas_focus(canvas_focus)

    def _draw_task_annotation_shape(
        self,
        annotation_definition: dict[str, object],
        color: str,
        show_indexes: bool = False,
        selected_point_index: int | None = None,
    ) -> None:
        if self._task_annotation_canvas is None:
            return
        points = annotation_definition.get("points", [])
        if not isinstance(points, list) or not points:
            return
        canvas_points = [self._to_task_canvas_point(point) for point in points if isinstance(point, dict) and "x" in point and "y" in point]
        if not canvas_points:
            return
        label_type = annotation_definition.get("type")

        if label_type == "Bounding box":
            if len(canvas_points) >= 2:
                (x0, y0), (x1, y1) = canvas_points[:2]
                self._task_annotation_canvas.create_rectangle(
                    x0,
                    y0,
                    x1,
                    y1,
                    outline=color,
                    width=2,
                    tags=("annotation_overlay",),
                )
            else:
                x0, y0 = canvas_points[0]
                self._task_annotation_canvas.create_oval(
                    x0 - 4,
                    y0 - 4,
                    x0 + 4,
                    y0 + 4,
                    fill=color,
                    outline="",
                    tags=("annotation_overlay",),
                )
            return

        if label_type in {"Polyline", "Skeleton", "Polygon", "Segmentacja (maska)"} and len(canvas_points) >= 2:
            flat_points = [value for point in canvas_points for value in point]
            self._task_annotation_canvas.create_line(*flat_points, fill=color, width=2, tags=("annotation_overlay",))
            if label_type in {"Polygon", "Segmentacja (maska)"} and len(canvas_points) >= 3:
                first_x, first_y = canvas_points[0]
                last_x, last_y = canvas_points[-1]
                self._task_annotation_canvas.create_line(
                    last_x,
                    last_y,
                    first_x,
                    first_y,
                    fill=color,
                    width=2,
                    tags=("annotation_overlay",),
                )

        for index, (x_pos, y_pos) in enumerate(canvas_points, start=1):
            point = points[index - 1] if index - 1 < len(points) and isinstance(points[index - 1], dict) else {}
            is_hidden_point = self._get_task_point_visibility(point) <= 0
            radius = 6 if selected_point_index == index - 1 else 4
            outline = "#fde68a" if selected_point_index == index - 1 else ("#cbd5e1" if is_hidden_point else "#ffffff")
            self._task_annotation_canvas.create_oval(
                x_pos - radius,
                y_pos - radius,
                x_pos + radius,
                y_pos + radius,
                fill="" if is_hidden_point else color,
                outline=outline,
                width=2 if selected_point_index == index - 1 else 1,
                tags=("annotation_overlay",),
            )
            if is_hidden_point:
                self._task_annotation_canvas.create_line(
                    x_pos - radius,
                    y_pos - radius,
                    x_pos + radius,
                    y_pos + radius,
                    fill=outline,
                    width=1,
                    tags=("annotation_overlay",),
                )
                self._task_annotation_canvas.create_line(
                    x_pos - radius,
                    y_pos + radius,
                    x_pos + radius,
                    y_pos - radius,
                    fill=outline,
                    width=1,
                    tags=("annotation_overlay",),
                )
            if show_indexes or label_type == "Skeleton":
                self._task_annotation_canvas.create_text(
                    x_pos + 8,
                    y_pos - 8,
                    text=str(index),
                    fill="#ffffff",
                    anchor="w",
                    tags=("annotation_overlay",),
                )

    def _toggle_selected_task_keypoint_visibility(self) -> None:
        label_id = self._resolve_task_label_id(self.task_label_var.get() if hasattr(self, "task_label_var") else "")
        label_template = self._task_label_templates_by_id.get(label_id)
        if label_template is None or label_template.label_type not in {"Point", "Skeleton"}:
            if self._task_status_var is not None:
                self._task_status_var.set("Ukrywanie pojedynczego keypointa jest dostepne tylko dla Point i Skeleton.")
            return

        point_index = self._task_selected_draft_point_index
        if point_index is None or point_index < 0 or point_index >= len(self._task_current_draft_points):
            if self._task_status_var is not None:
                self._task_status_var.set("Najpierw zaznacz keypoint na obrazie, a dopiero potem go ukryj lub odkryj.")
            return

        current_point = self._task_current_draft_points[point_index]
        new_visibility = 0 if self._get_task_point_visibility(current_point) > 0 else 2
        self._task_current_draft_points[point_index] = self._clone_task_point(current_point, visibility=new_visibility)
        self._render_task_annotation_overlay()
        if self._task_status_var is not None:
            action_text = "ukryty" if new_visibility == 0 else "odkryty"
            self._task_status_var.set(f"Wybrany keypoint został {action_text}.")

    def _toggle_selected_annotation(self, tree: ttk.Treeview) -> None:
        if not self._toggle_annotation_callback:
            return
        selected = tree.selection()
        if not selected:
            return
        annotation_id = self.annotation_ids_by_row.get(selected[0])
        if annotation_id is not None:
            self._toggle_annotation_callback(annotation_id)

    def _on_task_annotation_tree_selected(self, tree: ttk.Treeview) -> None:
        selected = tree.selection()
        self._task_selected_annotation_id = self.annotation_ids_by_row.get(selected[0]) if selected else None
        self._render_task_annotation_overlay()

    def _start_selected_annotation_reposition(self, tree: ttk.Treeview) -> None:
        selected = tree.selection()
        if not selected:
            if self._task_status_var is not None:
                self._task_status_var.set("Najpierw wybierz zapisany label z listy po prawej stronie.")
            return

        annotation_id = self.annotation_ids_by_row.get(selected[0])
        if annotation_id is None:
            return

        annotation = self._task_annotations_by_id.get(annotation_id)
        if annotation is None or annotation.annotation_definition is None:
            if self._task_status_var is not None:
                self._task_status_var.set("Wybrana annotacja nie ma zapisanej geometrii do przesuniecia.")
            return
        if annotation.label_type not in {"Point", "Skeleton"}:
            if self._task_status_var is not None:
                self._task_status_var.set("Przesuwanie zapisanych punktow jest dostepne tylko dla Point i Skeleton.")
            return
        if annotation.label_template_id is None:
            if self._task_status_var is not None:
                self._task_status_var.set("Nie mozna edytowac polozenia tej annotacji bez powiazanej etykiety.")
            return

        label_value = next(
            (
                value for value in self._task_label_values if value.startswith(f"{annotation.label_template_id}|")
            ),
            None,
        )
        if label_value is None:
            label_value = next(
                (
                    f"{label.id}|{label.name} [{label.label_type}]"
                    for label in self._task_label_templates_by_id.values()
                    if label.id == annotation.label_template_id
                ),
                None,
            )
        if label_value is None:
            if self._task_status_var is not None:
                self._task_status_var.set("Nie znaleziono etykiety powiazanej z wybrana annotacja.")
            return

        self.task_label_var.set(label_value)
        self._task_selected_label_value = label_value
        points = annotation.annotation_definition.get("points", [])
        self._task_current_draft_points = [
            self._clone_task_point(point, visibility=self._get_task_point_visibility(point))
            for point in points
            if isinstance(point, dict) and "x" in point and "y" in point
        ]
        self._task_editing_annotation_id = annotation_id
        self._task_selected_draft_point_index = None
        self._task_dragging_draft_point = False
        self._refresh_task_submit_button()
        self._render_task_annotation_overlay()
        if self._task_status_var is not None:
            self._task_status_var.set("Tryb zmiany polozenia aktywny. Przeciagaj punkty i kliknij 'Zapisz polozenie keypointow'.")

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

    def _open_task(self, task_id: int) -> None:
        self.selected_task_id = task_id
        if self._open_task_callback:
            self._open_task_callback(task_id)

    def _change_image(self, step: int) -> None:
        if self._task_editing_annotation_id is not None:
            if self._task_status_var is not None:
                self._task_status_var.set("Najpierw zapisz nowe polozenie keypointow albo wyczysc szkic, a dopiero potem zmien obraz.")
            return
        if self._change_image_callback:
            combo_value = self.task_label_var.get() if hasattr(self, "task_label_var") else ""
            self._change_image_callback(step, combo_value, self._build_task_annotation_definition())

    def _bind_task_navigation_keys(self) -> None:
        self.bind("<Left>", self._go_to_previous_image)
        self.bind("<Right>", self._go_to_next_image)

    def _go_to_previous_image(self, _event: tk.Event | None = None) -> str | None:
        if self._task_annotation_canvas is None:
            return None
        self._change_image(-1)
        return "break"

    def _go_to_next_image(self, _event: tk.Event | None = None) -> str | None:
        if self._task_annotation_canvas is None:
            return None
        self._change_image(1)
        return "break"

    def _reset_content(self) -> ttk.Frame:
        for widget in self.content.winfo_children():
            widget.destroy()
        self.unbind("<Left>")
        self.unbind("<Right>")
        self._task_label_templates_by_id = {}
        self._task_label_values = []
        self._task_current_annotations = []
        self._task_annotations_by_id = {}
        self._task_current_image_path = None
        self._task_current_draft_points = []
        self._task_selected_annotation_id = None
        self._task_editing_annotation_id = None
        self._task_selected_draft_point_index = None
        self._task_dragging_draft_point = False
        self._task_image_render_box = None
        self._task_image_photo = None
        self._task_annotation_image_item = None
        self._task_pending_canvas_focus = None
        self._task_status_var = None
        self._task_template_info_var = None
        self._task_template_preview_holder = None
        self._task_annotation_canvas = None
        self._task_submit_button = None
        frame = ttk.Frame(self.content)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        return frame

    def _render_preview(self, parent: ttk.Frame, image_path: str | None, size: tuple[int, int], fallback_text: str) -> None:
        for child in parent.winfo_children():
            child.destroy()

        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        background = ttk.Style(self).lookup(parent.cget("style"), "background") or self.cget("background")

        if image_path and Path(image_path).exists() and Image is not None and ImageTk is not None and ImageOps is not None:
            image = Image.open(image_path)
            image = ImageOps.contain(image, size)
            photo = ImageTk.PhotoImage(image)
            self._image_cache = photo
            label = tk.Label(parent, image=photo, background=background, borderwidth=0, highlightthickness=0)
            label.image = photo
            label.grid(row=0, column=0)
            return

        tk.Label(parent, text=fallback_text, anchor="center", justify="center", background=background, borderwidth=0).grid(
            row=0,
            column=0,
        )