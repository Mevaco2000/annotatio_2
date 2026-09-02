from __future__ import annotations

import ctypes
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


class HoverToolTip:
    def __init__(self, widget: tk.Widget, text_provider) -> None:
        self.widget = widget
        self.text_provider = text_provider
        self.tip_window: tk.Toplevel | None = None
        self.widget.bind("<Enter>", self._show, add="+")
        self.widget.bind("<Leave>", self._hide, add="+")
        self.widget.bind("<ButtonPress>", self._hide, add="+")
        self.widget.bind("<Destroy>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        text = self.text_provider() if callable(self.text_provider) else str(self.text_provider)
        if not text:
            return
        self._hide()
        x_pos = self.widget.winfo_rootx() + 16
        y_pos = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x_pos}+{y_pos}")
        tk.Label(
            self.tip_window,
            text=text,
            justify="left",
            wraplength=360,
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


class AppView(tk.Tk):
    SIDEBAR_EXPANDED_WIDTH = 180
    SIDEBAR_COLLAPSED_WIDTH = 64
    TITLEBAR_HEIGHT = 42
    TASK_CANVAS_WIDTH = 900
    TASK_CANVAS_HEIGHT = 620

    def __init__(self) -> None:
        super().__init__()
        self.title("annotat.io")
        self.minsize(1200, 800)
        self.configure(background="#0f172a")

        self._nav_callback = None
        self._create_project_callback = None
        self._export_project_callback = None
        self._import_dataset_callback = None
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
        self._auto_label_task_callback = None
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
        self._task_source_image = None
        self._task_source_image_path: str | None = None
        self._task_image_zoom = 1.0
        self._task_pending_canvas_focus: tuple[float, float, float, float] | None = None
        self._task_pending_zoom_canvas_anchor: tuple[float, float, float, float] | None = None
        self._task_zoom_var: tk.StringVar | None = None
        self._task_selected_label_value: str | None = None
        self._task_selected_annotation_id: int | None = None
        self._task_editing_annotation_id: int | None = None
        self._task_selected_draft_point_index: int | None = None
        self._task_dragging_draft_point = False
        self._task_dragging_new_bbox = False
        self._task_status_var: tk.StringVar | None = None
        self._task_template_info_var: tk.StringVar | None = None
        self._task_template_preview_holder: ttk.Frame | None = None
        self._task_annotation_canvas: tk.Canvas | None = None
        self._task_annotations_tree: ttk.Treeview | None = None
        self._task_annotation_image_item: int | None = None
        self._task_submit_button: ttk.Button | None = None
        self._task_page_frame: ttk.Frame | None = None
        self._task_page_task_id: int | None = None
        self._task_page_project_id: int | None = None
        self._task_header_label: ttk.Label | None = None
        self._task_counter_label: ttk.Label | None = None
        self._task_image_name_label: ttk.Label | None = None
        self._task_pan_start: tuple[float, float] | None = None
        self._task_is_panning = False
        self._task_dragging_annotation_body = False
        self._task_drag_last_canvas_point: tuple[float, float] | None = None
        self._task_tooltips: list[HoverToolTip] = []
        self._task_label_picker: tk.Toplevel | None = None
        self._task_syncing_tree_selection = False
        self._sidebar_expanded = True
        self._sidebar_title_label: ttk.Label | None = None
        self._sidebar_toggle_button: ttk.Button | None = None
        self._sidebar_nav_buttons: list[tuple[ttk.Button, str, str]] = []
        self._title_bar: tk.Frame | None = None
        self._title_bar_label: tk.Label | None = None
        self._minimize_button: tk.Button | None = None
        self._maximize_button: tk.Button | None = None
        self._close_button: tk.Button | None = None
        self._window_close_callback = None
        self._window_drag_offset: tuple[int, int] | None = None
        self._window_restore_geometry: str | None = None
        self._window_is_maximized = False

        self._configure_style()
        self._build_shell()
        self._install_custom_window_chrome()
        self._enforce_launch_window_state()

    def _enforce_launch_window_state(self) -> None:
        self.attributes("-topmost", False)
        self._maximize_to_work_area()
        self._update_title_bar_buttons()

    def _get_work_area_geometry(self) -> tuple[int, int, int, int]:
        try:
            if self.tk.call("tk", "windowingsystem") == "win32":
                rect = ctypes.wintypes.RECT()  # type: ignore[attr-defined]
                spi_get_work_area = 48
                if ctypes.windll.user32.SystemParametersInfoW(spi_get_work_area, 0, ctypes.byref(rect), 0):
                    width = max(1, int(rect.right - rect.left))
                    height = max(1, int(rect.bottom - rect.top))
                    return int(rect.left), int(rect.top), width, height
        except Exception:
            pass

        return 0, 0, int(self.winfo_screenwidth()), int(self.winfo_screenheight())

    def _maximize_to_work_area(self) -> None:
        try:
            self.update_idletasks()
            x_pos, y_pos, width, height = self._get_work_area_geometry()
            width = max(width, self.winfo_reqwidth(), 1200)
            height = max(height, self.winfo_reqheight(), 800)
            self.geometry(f"{width}x{height}+{x_pos}+{y_pos}")
            self._window_is_maximized = True
        except tk.TclError:
            return

    def _is_window_maximized(self) -> bool:
        return self._window_is_maximized

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Sidebar.TFrame", background="#1f2937")
        style.configure("Sidebar.TButton", background="#1f2937", foreground="#f9fafb", padding=10)
        style.map("Sidebar.TButton", background=[("active", "#374151")])
        style.configure("SidebarToggle.TButton", background="#1f2937", foreground="#f9fafb", padding=6)
        style.map("SidebarToggle.TButton", background=[("active", "#374151")])
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
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._title_bar = tk.Frame(self, bg="#0f172a", height=self.TITLEBAR_HEIGHT, highlightthickness=0, bd=0)
        self._title_bar.grid(row=0, column=0, sticky="ew")
        self._title_bar.grid_propagate(False)
        self._title_bar.columnconfigure(0, weight=1)

        title_container = tk.Frame(self._title_bar, bg="#0f172a", highlightthickness=0, bd=0)
        title_container.grid(row=0, column=0, sticky="ew")
        title_container.columnconfigure(0, weight=1)

        self._title_bar_label = tk.Label(
            title_container,
            text="annotat.io",
            bg="#0f172a",
            fg="#f8fafc",
            padx=16,
            pady=10,
            anchor="w",
            font=("Segoe UI", 11, "bold"),
        )
        self._title_bar_label.grid(row=0, column=0, sticky="ew")

        window_buttons = tk.Frame(title_container, bg="#0f172a", highlightthickness=0, bd=0)
        window_buttons.grid(row=0, column=1, sticky="e")

        self._minimize_button = tk.Button(
            window_buttons,
            text="_",
            command=self._minimize_window,
            bg="#0f172a",
            fg="#f8fafc",
            activebackground="#1e293b",
            activeforeground="#f8fafc",
            relief="flat",
            bd=0,
            padx=14,
            pady=8,
            highlightthickness=0,
        )
        self._minimize_button.grid(row=0, column=0)

        self._maximize_button = tk.Button(
            window_buttons,
            text="[]",
            command=self._toggle_maximize_window,
            bg="#0f172a",
            fg="#f8fafc",
            activebackground="#1e293b",
            activeforeground="#f8fafc",
            relief="flat",
            bd=0,
            padx=14,
            pady=8,
            highlightthickness=0,
        )
        self._maximize_button.grid(row=0, column=1)

        self._close_button = tk.Button(
            window_buttons,
            text="X",
            command=self._handle_window_close,
            bg="#0f172a",
            fg="#f8fafc",
            activebackground="#dc2626",
            activeforeground="#f8fafc",
            relief="flat",
            bd=0,
            padx=14,
            pady=8,
            highlightthickness=0,
        )
        self._close_button.grid(row=0, column=2)

        self._window_body = ttk.Frame(self)
        self._window_body.grid(row=1, column=0, sticky="nsew")
        self._window_body.columnconfigure(1, weight=1)
        self._window_body.rowconfigure(0, weight=1)

        self.sidebar = ttk.Frame(self._window_body, style="Sidebar.TFrame", width=self.SIDEBAR_EXPANDED_WIDTH)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)
        self.sidebar.columnconfigure(0, weight=1)

        sidebar_header = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        sidebar_header.grid(row=0, column=0, sticky="ew", padx=12, pady=(16, 20))
        sidebar_header.columnconfigure(0, weight=1)

        self._sidebar_toggle_button = ttk.Button(
            sidebar_header,
            text="<<",
            style="SidebarToggle.TButton",
            width=3,
            command=self._toggle_sidebar,
        )
        self._sidebar_toggle_button.grid(row=0, column=0, sticky="e")

        nav_items = [
            ("Start", "home"),
            ("Projects", "projects"),
            ("Settings", "settings"),
            ("Weryfikacja annotacji", "labels-checks"),
            ("Dokumentacja", "info"),
            ("Info", "info"),
        ]
        for index, (label, page_name) in enumerate(nav_items, start=1):
            collapsed_label = {
                "Start": "St",
                "Projects": "Pr",
                "Settings": "Se",
                "Weryfikacja annotacji": "Wa",
                "Dokumentacja": "Do",
                "Info": "In",
            }.get(label, label[:2])
            button = ttk.Button(
                self.sidebar,
                text=label,
                style="Sidebar.TButton",
                command=lambda value=page_name: self._nav_callback and self._nav_callback(value),
            )
            button.grid(row=index, column=0, sticky="ew", padx=12, pady=4)
            self._sidebar_nav_buttons.append((button, label, collapsed_label))

        self.content = ttk.Frame(self._window_body, padding=20)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)
        self._apply_sidebar_state()

    def _install_custom_window_chrome(self) -> None:
        self.overrideredirect(True)
        self.bind("<Map>", self._on_window_map)
        self.bind("<Escape>", self._on_escape_restore)
        if self._title_bar is not None:
            self._bind_title_bar_drag(self._title_bar)
        if self._title_bar_label is not None:
            self._bind_title_bar_drag(self._title_bar_label)

    def _bind_title_bar_drag(self, widget: tk.Widget) -> None:
        widget.bind("<ButtonPress-1>", self._on_title_bar_press)
        widget.bind("<B1-Motion>", self._on_title_bar_drag)
        widget.bind("<Double-Button-1>", lambda _event: self._toggle_maximize_window())

    def _on_title_bar_press(self, event: tk.Event) -> None:
        if self._is_window_maximized():
            self._window_drag_offset = None
            return
        self._window_drag_offset = (int(event.x_root - self.winfo_x()), int(event.y_root - self.winfo_y()))

    def _on_title_bar_drag(self, event: tk.Event) -> None:
        if self._is_window_maximized() or self._window_drag_offset is None:
            return
        offset_x, offset_y = self._window_drag_offset
        new_x = int(event.x_root - offset_x)
        new_y = int(event.y_root - offset_y)
        self.geometry(f"+{new_x}+{new_y}")

    def _minimize_window(self) -> None:
        self.overrideredirect(False)
        self.iconify()

    def _toggle_maximize_window(self) -> None:
        if self._is_window_maximized():
            self._window_is_maximized = False
            if self._window_restore_geometry is not None:
                self.geometry(self._window_restore_geometry)
        else:
            self._window_restore_geometry = self.geometry()
            self._maximize_to_work_area()
        self._update_title_bar_buttons()

    def _on_escape_restore(self, _event: tk.Event | None = None) -> str | None:
        if self._is_window_maximized():
            self._toggle_maximize_window()
            return "break"
        return None

    def _on_window_map(self, _event: tk.Event) -> None:
        if self.state() != "iconic":
            self.after_idle(self._restore_custom_window_chrome)
        self._update_title_bar_buttons()

    def _restore_custom_window_chrome(self) -> None:
        try:
            self.overrideredirect(True)
        except tk.TclError:
            return

    def _update_title_bar_buttons(self) -> None:
        if self._maximize_button is None:
            return
        self._maximize_button.configure(text="[]" if not self._is_window_maximized() else "<>")

    def _handle_window_close(self) -> None:
        if self._window_close_callback is not None:
            self._window_close_callback()
            return
        self.destroy()

    def _toggle_sidebar(self) -> None:
        self._sidebar_expanded = not self._sidebar_expanded
        self._apply_sidebar_state()

    def _apply_sidebar_state(self) -> None:
        sidebar_width = self.SIDEBAR_EXPANDED_WIDTH if self._sidebar_expanded else self.SIDEBAR_COLLAPSED_WIDTH
        self.sidebar.configure(width=sidebar_width)

        if self._sidebar_title_label is not None:
            if self._sidebar_expanded:
                self._sidebar_title_label.grid()
            else:
                self._sidebar_title_label.grid_remove()

        if self._sidebar_toggle_button is not None:
            self._sidebar_toggle_button.configure(text="<<" if self._sidebar_expanded else ">>")

        for button, expanded_label, collapsed_label in self._sidebar_nav_buttons:
            button.configure(text=expanded_label if self._sidebar_expanded else collapsed_label)

        self.sidebar.update_idletasks()

    def apply_session_state(self, session: SessionState) -> None:
        self.geometry(f"{session.window_width}x{session.window_height}")
        self._enforce_launch_window_state()

    def set_navigation_callback(self, callback) -> None:
        self._nav_callback = callback

    def set_create_project_callback(self, callback) -> None:
        self._create_project_callback = callback

    def set_export_project_callback(self, callback) -> None:
        self._export_project_callback = callback

    def set_import_dataset_callback(self, callback) -> None:
        self._import_dataset_callback = callback

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

    def set_auto_label_task_callback(self, callback) -> None:
        self._auto_label_task_callback = callback

    def set_run_last_model_callback(self, callback) -> None:
        self._run_last_model_callback = callback

    def set_copy_previous_annotation_callback(self, callback) -> None:
        self._copy_previous_annotation_callback = callback

    def set_change_image_callback(self, callback) -> None:
        self._change_image_callback = callback

    def set_close_callback(self, callback) -> None:
        self._window_close_callback = callback
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
        ttk.Button(toolbar, text="Import Dataset", command=self._import_dataset_callback).pack(side="right", padx=(8, 0))
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
        ttk.Button(toolbar, text="Import Dataset", command=self._import_dataset_callback).pack(side="right", padx=(8, 0))
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

        reuse_existing_layout = (
            self._task_page_frame is not None
            and self._task_page_frame.winfo_exists()
            and self._task_page_task_id == task.id
            and self._task_page_project_id == project.id
        )

        if reuse_existing_layout:
            self.refresh_task_page(workspace, image_index)
            return

        frame = self._reset_content()
        self._task_page_frame = frame
        self._task_page_task_id = task.id
        self._task_page_project_id = project.id
        frame.rowconfigure(0, weight=0)
        frame.rowconfigure(1, weight=0)
        frame.rowconfigure(2, weight=1)
        frame.rowconfigure(3, weight=0)
        frame.columnconfigure(0, weight=0, minsize=210)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=0, minsize=220)

        toolbar = ttk.Frame(frame)
        toolbar.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 12))
        toolbar.columnconfigure(0, weight=1)

        toolbar_row = ttk.Frame(toolbar)
        toolbar_row.grid(row=0, column=0, sticky="w")

        back_button = ttk.Button(toolbar_row, text="Powrot", command=lambda: self._open_project(project.id))
        back_button.pack(side="left")
        delete_image_button = ttk.Button(toolbar_row, text="Usun zdjecie", command=self._delete_image_callback)
        delete_image_button.pack(side="left", padx=(8, 0))
        auto_label_button = ttk.Button(toolbar_row, text="Auto label obraz", command=self._auto_label_callback)
        auto_label_button.pack(side="left", padx=(8, 0))

        auto_label_task_button = ttk.Button(toolbar_row, text="Auto label task", command=self._auto_label_task_callback)
        auto_label_task_button.pack(side="left", padx=(8, 0))
        run_last_model_button = ttk.Button(toolbar_row, text="Ostatni model", command=self._run_last_model_callback)
        run_last_model_button.pack(side="left", padx=(8, 0))

        counter_text = "0/0"
        current_image = None
        current_annotations = []
        if images:
            current_image = images[image_index]
            current_annotations = annotations_by_image.get(current_image.id, [])
            counter_text = f"{image_index + 1}/{len(images)}"

        self._task_header_label = ttk.Label(frame, text=f"{project.name} / {task.name}", style="Header.TLabel")
        self._task_header_label.grid(row=0, column=0, columnspan=2, sticky="w")
        self._task_counter_label = ttk.Label(frame, text=counter_text)
        self._task_counter_label.grid(row=0, column=2, sticky="e")

        self._task_label_templates_by_id = {item.id: item for item in label_templates if item.id is not None}
        self._task_current_annotations = current_annotations
        self._task_annotations_by_id = {item.id: item for item in current_annotations}
        self._task_current_image_path = current_image.file_path if current_image else None
        self._task_current_draft_points = []
        supports_keypoint_annotations = any(item.label_type in {"Point", "Skeleton"} for item in label_templates)
        available_annotation_ids = set(self._task_annotations_by_id)
        if self._task_selected_annotation_id not in available_annotation_ids:
            self._task_selected_annotation_id = None
        self._task_editing_annotation_id = None
        label_values = [f"{item.id}|{item.name} [{item.label_type}]" for item in label_templates]
        self._task_label_values = label_values
        selected_label_value = self._task_selected_label_value if self._task_selected_label_value in label_values else (label_values[0] if label_values else "")
        self.task_label_var = tk.StringVar(value=selected_label_value)
        self._task_status_var = tk.StringVar(value="Wybierz etykiete, aby annotowac obraz.")
        left_panel = ttk.Frame(frame, padding=(0, 12, 4, 12))
        left_panel.grid(row=2, column=0, sticky="nsew")
        left_panel.columnconfigure(0, weight=0)
        for row_index in range(10):
            left_panel.rowconfigure(row_index, weight=1)
        self._bind_task_navigation_keys()

        ttk.Label(left_panel, text="Narzędzia annotacji", style="SubHeader.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self._task_submit_button = ttk.Button(
            left_panel,
            text="Add label (N)",
            command=self._request_task_submit,
        )
        self._task_submit_button.grid(row=1, column=0, sticky="w", pady=4)
        clear_draft_button = ttk.Button(left_panel, text="Clear (C)", command=self._clear_task_annotation_draft)
        clear_draft_button.grid(row=2, column=0, sticky="w", pady=4)
        copy_previous_button = ttk.Button(left_panel, text="Copy from\nprev (V)", command=self._copy_task_annotation_from_previous_image)
        copy_previous_button.grid(
            row=3,
            column=0,
            sticky="w",
            pady=4,
        )
        undo_point_button = ttk.Button(left_panel, text="Undo", command=self._undo_task_annotation_point)
        undo_point_button.grid(row=4, column=0, sticky="w", pady=4)
        toggle_keypoint_button: ttk.Button | None = None
        if supports_keypoint_annotations:
            toggle_keypoint_button = ttk.Button(
                left_panel,
                text="Ukryj/Odkryj keypoint",
                command=self._toggle_selected_task_keypoint_visibility,
            )
            toggle_keypoint_button.grid(row=5, column=0, sticky="w", pady=4)

        self._task_image_zoom = 1.15
        self._task_zoom_var = tk.StringVar(value=f"Zoom: {round(self._task_image_zoom * 100):d}%")

        center_panel = ttk.Frame(frame, padding=(0, 12, 12, 12))
        center_panel.grid(row=2, column=1, sticky="nsew")
        center_panel.columnconfigure(0, weight=1)
        center_panel.rowconfigure(2, weight=1)

        label_row = ttk.Frame(center_panel)
        label_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        label_row.columnconfigure(1, weight=1)
        ttk.Label(label_row, text="Aktywna etykieta", style="SubHeader.TLabel").grid(row=0, column=0, sticky="w")
        label_combo = ttk.Combobox(label_row, textvariable=self.task_label_var, values=label_values, state="readonly", width=44)
        label_combo.grid(row=0, column=1, sticky="ew", padx=(12, 0))
        label_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_task_label_selected(self.task_label_var.get()))

        image_name = Path(current_image.file_path).name if current_image else "Brak obrazu"
        self._task_image_name_label = ttk.Label(center_panel, text=image_name, style="SubHeader.TLabel")
        self._task_image_name_label.grid(row=1, column=0, sticky="n", pady=(0, 8))

        image_holder = ttk.Frame(center_panel, style="Card.TFrame", padding=12)
        image_holder.grid(row=2, column=0, sticky="nsew", padx=(0, 4), pady=0)
        image_holder.columnconfigure(0, weight=1)
        image_holder.rowconfigure(0, weight=1)
        task_canvas_scroll_y = ttk.Scrollbar(image_holder, orient="vertical")
        task_canvas_scroll_x = ttk.Scrollbar(image_holder, orient="horizontal")
        self._task_annotation_canvas = tk.Canvas(
            image_holder,
            width=self.TASK_CANVAS_WIDTH,
            height=self.TASK_CANVAS_HEIGHT,
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
        self._task_annotation_canvas.bind("<ButtonPress-3>", self._on_task_pan_start)
        self._task_annotation_canvas.bind("<B3-Motion>", self._on_task_pan_drag)
        self._task_annotation_canvas.bind("<ButtonRelease-3>", self._on_task_pan_end)
        self._render_task_annotation_canvas()

        if label_values:
            self._on_task_label_selected(self.task_label_var.get())

        nav_row = ttk.Frame(center_panel)
        nav_row.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        nav_row.columnconfigure(0, weight=1)
        nav_row.columnconfigure(1, weight=0)
        nav_row.columnconfigure(2, weight=1)
        ttk.Button(nav_row, text="Poprzednie", command=lambda: self._change_image(-1)).grid(row=0, column=0, sticky="w")

        zoom_controls = ttk.Frame(nav_row)
        zoom_controls.grid(row=0, column=1, sticky="n", padx=16)
        zoom_controls.columnconfigure(1, weight=1)
        zoom_out_button = ttk.Button(zoom_controls, text="-", width=3, command=lambda: self._change_task_zoom(-0.25))
        zoom_out_button.grid(row=0, column=0)
        ttk.Label(zoom_controls, textvariable=self._task_zoom_var).grid(row=0, column=1, padx=8, sticky="ew")
        zoom_in_button = ttk.Button(zoom_controls, text="+", width=3, command=lambda: self._change_task_zoom(0.25))
        zoom_in_button.grid(row=0, column=2)
        zoom_reset_button = ttk.Button(zoom_controls, text="Reset", command=self._reset_task_zoom)
        zoom_reset_button.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))

        ttk.Button(nav_row, text="Nastepne", command=lambda: self._change_image(1)).grid(row=0, column=2, sticky="e")

        ttk.Label(frame, textvariable=self._task_status_var, justify="left", wraplength=1100).grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(8, 0),
        )

        right_panel = ttk.Frame(frame, padding=(8, 12, 0, 12))
        right_panel.grid(row=2, column=2, sticky="nsew")
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(1, weight=1)
        ttk.Label(right_panel, text="Widoczne label'e", style="SubHeader.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))

        tree = ttk.Treeview(right_panel, columns=("type_short", "label", "source", "visible"), show="headings", height=14)
        tree.grid(row=1, column=0, sticky="nsew")
        self._task_annotations_tree = tree
        tree.heading("type_short", text="T")
        tree.heading("label", text="Etykieta")
        tree.heading("source", text="Zrodlo")
        tree.heading("visible", text="Widoczny")
        tree.column("type_short", width=34, anchor="center")
        tree.column("label", width=124, anchor="w")
        tree.column("source", width=58, anchor="center")
        tree.column("visible", width=62, anchor="center")

        self.annotation_ids_by_row = {}
        selected_row_id: str | None = None
        for annotation in current_annotations:
            row_id = tree.insert(
                "",
                "end",
                values=(
                    self._label_type_short_name(annotation.label_type),
                    annotation.label_name,
                    annotation.source,
                    "tak" if annotation.is_visible else "nie",
                ),
            )
            self.annotation_ids_by_row[row_id] = annotation.id
            if annotation.id == self._task_selected_annotation_id:
                selected_row_id = row_id

        tree.bind("<<TreeviewSelect>>", lambda _event: self._on_task_annotation_tree_selected(tree))
        if selected_row_id is not None:
            tree.selection_set(selected_row_id)
            tree.focus(selected_row_id)

        button_row = ttk.Frame(right_panel)
        button_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        toggle_button = ttk.Button(button_row, text="Ukryj/Pokaz", command=lambda: self._toggle_selected_annotation(tree))
        toggle_button.pack(side="left")
        delete_button = ttk.Button(button_row, text="Usun label (Delete)", command=self._delete_selected_annotation)
        delete_button.pack(side="left", padx=(8, 0))

        self._task_tooltips = [
            HoverToolTip(back_button, "Powrot do strony projektu"),
            HoverToolTip(delete_image_button, "Usun aktualnie wyswietlane zdjecie z taska"),
            HoverToolTip(auto_label_button, "Uruchom model dla biezacego zdjecia"),
            HoverToolTip(auto_label_task_button, "Uruchom model dla wszystkich zdjec w tasku"),
            HoverToolTip(run_last_model_button, "Powtorz ostatnia konfiguracje modelu dla biezacego zdjecia"),
            HoverToolTip(self._task_submit_button, "Add label (N)"),
            HoverToolTip(clear_draft_button, "Clear (C)"),
            HoverToolTip(copy_previous_button, "Copy from prev (V)"),
            HoverToolTip(undo_point_button, "Undo"),
            HoverToolTip(zoom_out_button, "Pomniejsz widok"),
            HoverToolTip(zoom_in_button, "Powieksz widok"),
            HoverToolTip(zoom_reset_button, "Resetuj zoom do 100%"),
            HoverToolTip(toggle_button, "Zmien widocznosc zaznaczonego labela"),
            HoverToolTip(delete_button, "Usun label (Delete)"),
        ]
        if toggle_keypoint_button is not None:
            self._task_tooltips.append(HoverToolTip(toggle_keypoint_button, "Ukryj/Odkryj keypoint"))

    def refresh_task_page(self, workspace: dict, image_index: int) -> None:
        if self._task_page_frame is None or not self._task_page_frame.winfo_exists():
            self.show_task_page(workspace, image_index)
            return
        if self._task_annotation_canvas is None or self._task_annotations_tree is None:
            self.show_task_page(workspace, image_index)
            return

        project = workspace["project"]
        task = workspace["task"]
        label_templates = workspace["labels"]
        images = workspace["images"]
        annotations_by_image = workspace["annotations"]

        if self._task_page_task_id != task.id or self._task_page_project_id != project.id:
            self.show_task_page(workspace, image_index)
            return

        previous_image_path = self._task_current_image_path
        viewport_focus = self._get_task_canvas_focus()

        counter_text = "0/0"
        current_image = None
        current_annotations: list[AnnotationRecord] = []
        if images:
            safe_index = max(0, min(image_index, len(images) - 1))
            current_image = images[safe_index]
            current_annotations = annotations_by_image.get(current_image.id, [])
            counter_text = f"{safe_index + 1}/{len(images)}"

        if self._task_header_label is not None and self._task_header_label.winfo_exists():
            self._task_header_label.configure(text=f"{project.name} / {task.name}")
        if self._task_counter_label is not None and self._task_counter_label.winfo_exists():
            self._task_counter_label.configure(text=counter_text)
        if self._task_image_name_label is not None and self._task_image_name_label.winfo_exists():
            self._task_image_name_label.configure(text=Path(current_image.file_path).name if current_image else "Brak obrazu")

        self._task_label_templates_by_id = {item.id: item for item in label_templates if item.id is not None}
        self._task_current_annotations = current_annotations
        self._task_annotations_by_id = {item.id: item for item in current_annotations}
        self._task_current_image_path = current_image.file_path if current_image else None
        self._task_current_draft_points = []
        self._task_selected_draft_point_index = None
        self._task_dragging_draft_point = False
        self._task_dragging_new_bbox = False
        self._task_dragging_annotation_body = False
        self._task_drag_last_canvas_point = None
        self._task_editing_annotation_id = None
        self._refresh_task_submit_button()

        available_annotation_ids = set(self._task_annotations_by_id)
        if self._task_selected_annotation_id not in available_annotation_ids:
            self._task_selected_annotation_id = None

        tree = self._task_annotations_tree
        tree.delete(*tree.get_children())
        self.annotation_ids_by_row = {}
        selected_row_id: str | None = None
        for annotation in current_annotations:
            row_id = tree.insert(
                "",
                "end",
                values=(
                    self._label_type_short_name(annotation.label_type),
                    annotation.label_name,
                    annotation.source,
                    "tak" if annotation.is_visible else "nie",
                ),
            )
            self.annotation_ids_by_row[row_id] = annotation.id
            if annotation.id == self._task_selected_annotation_id:
                selected_row_id = row_id

        if selected_row_id is not None:
            self._task_syncing_tree_selection = True
            tree.selection_set(selected_row_id)
            self._task_syncing_tree_selection = False
            tree.focus(selected_row_id)
            tree.see(selected_row_id)

        label_id = self._resolve_task_label_id(self.task_label_var.get() if hasattr(self, "task_label_var") else "")
        label_template = self._task_label_templates_by_id.get(label_id)
        if self._task_status_var is not None and label_template is not None:
            self._task_status_var.set(self._describe_task_draft_state(label_template, label_template.preview_definition))

        should_redraw_full_canvas = self._task_current_image_path != previous_image_path or self._task_image_render_box is None
        if not should_redraw_full_canvas:
            self._render_task_annotation_overlay()
            return

        if viewport_focus is not None:
            self._task_pending_canvas_focus = viewport_focus

        self._render_task_annotation_canvas()

    def show_settings_page(self, description: str) -> None:
        frame = self._reset_content()
        ttk.Label(frame, text="Settings", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=description, justify="left", wraplength=820).grid(row=1, column=0, sticky="nw", pady=(16, 0))

    def show_labels_checks_page(self, description: str) -> None:
        frame = self._reset_content()
        ttk.Label(frame, text="Weryfikacja annotacji", style="Header.TLabel").grid(row=0, column=0, sticky="w")
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
        button_text = "Save label (N)" if self._task_editing_annotation_id is not None else "Add label (N)"
        self._task_submit_button.configure(text=button_text)

    def _request_task_submit(self) -> None:
        if self._task_editing_annotation_id is not None:
            self._handle_task_annotation_submit()
            return
        if not self._task_label_values:
            return
        if len(self._task_label_values) == 1:
            self.task_label_var.set(self._task_label_values[0])
            self._task_selected_label_value = self._task_label_values[0]
            self._on_task_label_selected(self.task_label_var.get())
            self._handle_task_annotation_submit()
            return
        self._show_task_label_picker()

    def _show_task_label_picker(self) -> None:
        if self._task_label_picker is not None and self._task_label_picker.winfo_exists():
            self._task_label_picker.destroy()

        popup = tk.Toplevel(self)
        popup.title("Wybierz etykiete")
        popup.transient(self)
        popup.resizable(False, False)
        popup.columnconfigure(0, weight=1)
        popup.rowconfigure(0, weight=1)

        current_value = self.task_label_var.get() if hasattr(self, "task_label_var") else ""
        if current_value not in self._task_label_values:
            current_value = self._task_label_values[0]
        selected_var = tk.StringVar(value=current_value)

        container = ttk.Frame(popup, padding=10)
        container.grid(sticky="nsew")
        container.columnconfigure(0, weight=1)

        ttk.Label(container, text="Wybierz etykiete do dodania").grid(row=0, column=0, sticky="w")
        selector = ttk.Combobox(container, textvariable=selected_var, values=self._task_label_values, state="readonly", width=48)
        selector.grid(row=1, column=0, sticky="ew", pady=(6, 10))

        actions = ttk.Frame(container)
        actions.grid(row=2, column=0, sticky="e")

        def _accept() -> None:
            selected_value = selected_var.get().strip()
            if not selected_value:
                return
            self.task_label_var.set(selected_value)
            self._task_selected_label_value = selected_value
            self._on_task_label_selected(selected_value)
            if popup.winfo_exists():
                popup.destroy()
            self._task_label_picker = None
            self._handle_task_annotation_submit()

        def _cancel() -> None:
            if popup.winfo_exists():
                popup.destroy()
            self._task_label_picker = None

        ttk.Button(actions, text="Anuluj", command=_cancel).pack(side="right", padx=(8, 0))
        ttk.Button(actions, text="Wybierz", command=_accept).pack(side="right")

        popup.bind("<Return>", lambda _event: _accept())
        popup.bind("<Escape>", lambda _event: _cancel())

        popup.update_idletasks()
        if self._task_submit_button is not None and self._task_submit_button.winfo_exists():
            x_pos = self._task_submit_button.winfo_rootx()
            y_pos = self._task_submit_button.winfo_rooty() + self._task_submit_button.winfo_height() + 8
        else:
            x_pos = self.winfo_rootx() + max(0, (self.winfo_width() - popup.winfo_reqwidth()) // 2)
            y_pos = self.winfo_rooty() + 120
        popup.geometry(f"+{x_pos}+{y_pos}")
        popup.grab_set()
        selector.focus_set()
        self._task_label_picker = popup

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
            return "Nacisnij i przeciagnij myszka, aby narysowac bounding box na aktualnym obrazie."
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

        if self._is_task_bbox_draft_active():
            corners = self._get_bbox_corner_points(self._task_current_draft_points)
            best_corner_index: int | None = None
            best_corner_distance = radius * radius
            for corner_index, corner in enumerate(corners):
                point_x, point_y = self._to_task_canvas_point(corner)
                distance = (point_x - canvas_x) ** 2 + (point_y - canvas_y) ** 2
                if distance <= best_corner_distance:
                    best_corner_distance = distance
                    best_corner_index = corner_index
            return best_corner_index

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
        max_viewport_x = max(0.0, viewport_width - 1.0)
        max_viewport_y = max(0.0, viewport_height - 1.0)
        anchor_viewport_x = float(viewport_x) if viewport_x is not None else viewport_width / 2
        anchor_viewport_y = float(viewport_y) if viewport_y is not None else viewport_height / 2
        anchor_viewport_x = min(max_viewport_x, max(0.0, anchor_viewport_x))
        anchor_viewport_y = min(max_viewport_y, max(0.0, anchor_viewport_y))
        anchor_canvas_x = float(canvas.canvasx(anchor_viewport_x))
        anchor_canvas_y = float(canvas.canvasy(anchor_viewport_y))
        x0, y0, x1, y1 = self._task_image_render_box
        image_width = max(1.0, x1 - x0)
        image_height = max(1.0, y1 - y0)
        relative_x = (anchor_canvas_x - x0) / image_width
        relative_y = (anchor_canvas_y - y0) / image_height
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
        anchor_viewport_x = min(max(0.0, viewport_width - 1.0), max(0.0, focus[2]))
        anchor_viewport_y = min(max(0.0, viewport_height - 1.0), max(0.0, focus[3]))

        current_anchor_x = float(canvas.canvasx(anchor_viewport_x))
        current_anchor_y = float(canvas.canvasy(anchor_viewport_y))
        delta_x = target_anchor_x - current_anchor_x
        delta_y = target_anchor_y - current_anchor_y

        if region_width <= viewport_width:
            canvas.xview_moveto(0)
        else:
            current_left = float(canvas.canvasx(0.0))
            target_left = current_left + delta_x
            x_fraction = (target_left - region_left) / max(1.0, region_width - viewport_width)
            canvas.xview_moveto(min(1.0, max(0.0, x_fraction)))

        if region_height <= viewport_height:
            canvas.yview_moveto(0)
        else:
            current_top = float(canvas.canvasy(0.0))
            target_top = current_top + delta_y
            y_fraction = (target_top - region_top) / max(1.0, region_height - viewport_height)
            canvas.yview_moveto(min(1.0, max(0.0, y_fraction)))

        # Second pass: correct residual drift caused by image-size rounding during zoom.
        for _ in range(2):
            current_anchor_x = float(canvas.canvasx(anchor_viewport_x))
            current_anchor_y = float(canvas.canvasy(anchor_viewport_y))
            error_x = target_anchor_x - current_anchor_x
            error_y = target_anchor_y - current_anchor_y
            if abs(error_x) < 0.25 and abs(error_y) < 0.25:
                break

            if region_width > viewport_width:
                current_left = float(canvas.canvasx(0.0))
                target_left = current_left + error_x
                x_fraction = (target_left - region_left) / max(1.0, region_width - viewport_width)
                canvas.xview_moveto(min(1.0, max(0.0, x_fraction)))

            if region_height > viewport_height:
                current_top = float(canvas.canvasy(0.0))
                target_top = current_top + error_y
                y_fraction = (target_top - region_top) / max(1.0, region_height - viewport_height)
                canvas.yview_moveto(min(1.0, max(0.0, y_fraction)))

    def _change_task_zoom(self, delta: float, focus: tuple[float, float, float, float] | None = None) -> None:
        new_zoom = min(6.0, max(1.0, round(self._task_image_zoom + delta, 2)))
        if abs(new_zoom - self._task_image_zoom) < 1e-9:
            return
        if self._task_pending_zoom_canvas_anchor is None:
            self._task_pending_canvas_focus = focus or self._get_task_canvas_focus() or self._default_task_canvas_focus()
        self._task_image_zoom = new_zoom
        if self._task_zoom_var is not None:
            self._task_zoom_var.set(f"Zoom: {round(self._task_image_zoom * 100):d}%")
        self._render_task_annotation_canvas()

    def _reset_task_zoom(self) -> None:
        self._task_pending_canvas_focus = self._default_task_canvas_focus()
        self._task_image_zoom = 1.0
        if self._task_zoom_var is not None:
            self._task_zoom_var.set("Zoom: 100%")
        self._render_task_annotation_canvas()

    def _default_task_canvas_focus(self) -> tuple[float, float, float, float]:
        canvas = self._task_annotation_canvas
        if canvas is None:
            return (0.5, 0.5, float(self.TASK_CANVAS_WIDTH) / 2, float(self.TASK_CANVAS_HEIGHT) / 2)
        canvas.update_idletasks()
        viewport_width = float(canvas.winfo_width())
        viewport_height = float(canvas.winfo_height())
        if viewport_width <= 1.0:
            viewport_width = float(self.TASK_CANVAS_WIDTH)
        if viewport_height <= 1.0:
            viewport_height = float(self.TASK_CANVAS_HEIGHT)
        return (0.5, 0.5, viewport_width / 2, viewport_height / 2)

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

        pointer_x = float(event.x)
        pointer_y = float(event.y)

        viewport_width = max(1.0, float(self._task_annotation_canvas.winfo_width()))
        viewport_height = max(1.0, float(self._task_annotation_canvas.winfo_height()))
        pointer_x = min(max(0.0, viewport_width - 1.0), max(0.0, pointer_x))
        pointer_y = min(max(0.0, viewport_height - 1.0), max(0.0, pointer_y))

        if self._task_image_render_box is not None:
            x0, y0, x1, y1 = self._task_image_render_box
            anchor_canvas_x = float(self._task_annotation_canvas.canvasx(pointer_x))
            anchor_canvas_y = float(self._task_annotation_canvas.canvasy(pointer_y))
            image_width = max(1.0, float(x1 - x0))
            image_height = max(1.0, float(y1 - y0))
            local_x = (anchor_canvas_x - float(x0)) / image_width
            local_y = (anchor_canvas_y - float(y0)) / image_height
            self._task_pending_zoom_canvas_anchor = (local_x, local_y, anchor_canvas_x, anchor_canvas_y)

        self._change_task_zoom(0.1 if delta > 0 else -0.1)
        return "break"

    def _on_task_image_press(self, event: tk.Event) -> None:
        if self._task_is_panning:
            return

        label_id = self._resolve_task_label_id(self.task_label_var.get() if hasattr(self, "task_label_var") else "")
        label_template = self._task_label_templates_by_id.get(label_id)
        canvas_x, canvas_y = self._get_task_canvas_event_coords(event)

        hit_annotation_id = self._find_annotation_at_canvas_point(canvas_x, canvas_y)
        if hit_annotation_id is not None:
            self._select_annotation_by_id(hit_annotation_id)
            self._start_annotation_edit(hit_annotation_id)
            point_index = self._find_task_draft_point_index(canvas_x, canvas_y)
            if point_index is not None:
                self._task_selected_draft_point_index = point_index
                self._task_dragging_draft_point = False
                self._task_dragging_annotation_body = False
                self._task_drag_last_canvas_point = None
            else:
                self._task_selected_draft_point_index = None
                self._task_dragging_annotation_body = True
                self._task_drag_last_canvas_point = (canvas_x, canvas_y)
            self._render_task_annotation_overlay()
            return

        point_index = self._find_task_draft_point_index(canvas_x, canvas_y)
        if point_index is not None:
            self._task_selected_draft_point_index = point_index
            self._task_dragging_draft_point = False
            self._task_dragging_new_bbox = False
            self._render_task_annotation_overlay()
            return
        self._task_selected_draft_point_index = None
        self._task_dragging_draft_point = False
        self._task_dragging_new_bbox = False
        self._task_dragging_annotation_body = False
        self._task_drag_last_canvas_point = None
        if label_template is not None and label_template.label_type == "Bounding box" and self._task_editing_annotation_id is None:
            point = self._to_task_normalized_point(canvas_x, canvas_y)
            if point is None:
                return
            cloned_point = self._clone_task_point(point)
            self._task_current_draft_points = [cloned_point, self._clone_task_point(point)]
            self._task_dragging_new_bbox = True
            self._render_task_annotation_overlay()
            if self._task_status_var is not None:
                self._task_status_var.set("Przeciagaj myszka, aby okreslic przeciwlegly rog bounding boxa.")
            return
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
            if self._task_status_var is not None:
                self._task_status_var.set("Bounding box rysuje sie przez przeciaganie myszka na obrazie.")
            return
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
        if self._task_dragging_annotation_body and self._task_drag_last_canvas_point is not None:
            if self._task_image_render_box is None or not self._task_current_draft_points:
                self._task_dragging_annotation_body = False
                self._task_drag_last_canvas_point = None
                return
            previous_x, previous_y = self._task_drag_last_canvas_point
            current_x, current_y = self._get_task_canvas_event_coords(event)
            x0, y0, x1, y1 = self._task_image_render_box
            width = max(1.0, x1 - x0)
            height = max(1.0, y1 - y0)
            delta_x = (current_x - previous_x) / width
            delta_y = (current_y - previous_y) / height
            if abs(delta_x) > 1e-12 or abs(delta_y) > 1e-12:
                shifted_points: list[dict[str, float]] = []
                for point in self._task_current_draft_points:
                    shifted_points.append(
                        {
                            "x": round(min(1.0, max(0.0, float(point.get("x", 0.0)) + delta_x)), 4),
                            "y": round(min(1.0, max(0.0, float(point.get("y", 0.0)) + delta_y)), 4),
                            **({"visibility": 0} if self._get_task_point_visibility(point) <= 0 else {}),
                        }
                    )
                self._task_current_draft_points = shifted_points
                self._render_task_annotation_overlay()
            self._task_drag_last_canvas_point = (current_x, current_y)
            return

        if self._task_dragging_new_bbox:
            if len(self._task_current_draft_points) < 2:
                self._task_dragging_new_bbox = False
                return
            canvas_x, canvas_y = self._get_task_canvas_event_coords(event)
            point = self._to_task_normalized_point(canvas_x, canvas_y)
            if point is None:
                return
            first_point = self._task_current_draft_points[0]
            self._task_current_draft_points = [
                self._clone_task_point(first_point, visibility=self._get_task_point_visibility(first_point)),
                self._clone_task_point(point),
            ]
            self._render_task_annotation_overlay()
            return

        point_index = self._task_selected_draft_point_index
        if point_index is None:
            return

        canvas_x, canvas_y = self._get_task_canvas_event_coords(event)
        point = self._to_task_normalized_point(canvas_x, canvas_y)
        if point is None:
            return

        if self._is_task_bbox_draft_active() and 0 <= point_index <= 3:
            self._apply_bbox_corner_drag(point_index, point)
            self._task_dragging_draft_point = True
            self._render_task_annotation_overlay()
            return

        if point_index < 0 or point_index >= len(self._task_current_draft_points):
            self._task_selected_draft_point_index = None
            return

        current_point = self._task_current_draft_points[point_index]
        self._task_current_draft_points[point_index] = self._clone_task_point(point, visibility=self._get_task_point_visibility(current_point))
        self._task_dragging_draft_point = True
        self._render_task_annotation_overlay()

    def _on_task_image_release(self, _event: tk.Event) -> None:
        if self._task_dragging_annotation_body:
            self._task_dragging_annotation_body = False
            self._task_drag_last_canvas_point = None
            self._render_task_annotation_overlay()
            return
        if self._task_dragging_new_bbox:
            self._task_dragging_new_bbox = False
            if len(self._task_current_draft_points) >= 2:
                start_point = self._task_current_draft_points[0]
                end_point = self._task_current_draft_points[1]
                if start_point["x"] == end_point["x"] and start_point["y"] == end_point["y"]:
                    self._task_current_draft_points = []
                    label_id = self._resolve_task_label_id(self.task_label_var.get() if hasattr(self, "task_label_var") else "")
                    label_template = self._task_label_templates_by_id.get(label_id)
                    if label_template is not None and self._task_status_var is not None:
                        self._task_status_var.set(self._describe_task_draft_state(label_template, label_template.preview_definition))
                    self._render_task_annotation_overlay()
                    return
                self._render_task_annotation_overlay()
                self._submit_annotation(
                    self.task_label_var.get() if hasattr(self, "task_label_var") else "",
                    "",
                    self._build_task_annotation_definition(),
                )
            return
        if self._task_selected_draft_point_index is None:
            return
        self._task_dragging_draft_point = False
        self._render_task_annotation_overlay()

    def _undo_task_annotation_point(self) -> None:
        if not self._task_current_draft_points:
            return
        if len(self._task_current_draft_points) == 2:
            label_id = self._resolve_task_label_id(self.task_label_var.get() if hasattr(self, "task_label_var") else "")
            label_template = self._task_label_templates_by_id.get(label_id)
            if label_template is not None and label_template.label_type == "Bounding box":
                self._task_current_draft_points = []
                self._task_selected_draft_point_index = None
                self._task_dragging_draft_point = False
                self._task_dragging_new_bbox = False
                self._task_dragging_annotation_body = False
                self._task_drag_last_canvas_point = None
                self._render_task_annotation_overlay()
                if self._task_status_var is not None:
                    self._task_status_var.set(self._describe_task_draft_state(label_template, label_template.preview_definition))
                return
        self._task_current_draft_points.pop()
        self._task_selected_draft_point_index = None
        self._task_dragging_draft_point = False
        self._task_dragging_new_bbox = False
        self._task_dragging_annotation_body = False
        self._task_drag_last_canvas_point = None
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
        self._task_dragging_new_bbox = False
        self._task_dragging_annotation_body = False
        self._task_drag_last_canvas_point = None
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

    def _is_task_bbox_draft_active(self) -> bool:
        if len(self._task_current_draft_points) < 2:
            return False
        label_id = self._resolve_task_label_id(self.task_label_var.get() if hasattr(self, "task_label_var") else "")
        label_template = self._task_label_templates_by_id.get(label_id)
        return label_template is not None and label_template.label_type == "Bounding box"

    def _get_bbox_corner_points(self, points: list[dict[str, float]]) -> list[dict[str, float]]:
        if len(points) < 2:
            return []
        x_values = [float(points[0].get("x", 0.0)), float(points[1].get("x", 0.0))]
        y_values = [float(points[0].get("y", 0.0)), float(points[1].get("y", 0.0))]
        left = min(x_values)
        right = max(x_values)
        top = min(y_values)
        bottom = max(y_values)
        return [
            {"x": left, "y": top},
            {"x": right, "y": bottom},
            {"x": right, "y": top},
            {"x": left, "y": bottom},
        ]

    def _apply_bbox_corner_drag(self, corner_index: int, point: dict[str, float]) -> None:
        if len(self._task_current_draft_points) < 2:
            return
        if corner_index < 0 or corner_index > 3:
            return

        first_point, second_point = self._task_current_draft_points[:2]
        left = min(float(first_point.get("x", 0.0)), float(second_point.get("x", 0.0)))
        right = max(float(first_point.get("x", 0.0)), float(second_point.get("x", 0.0)))
        top = min(float(first_point.get("y", 0.0)), float(second_point.get("y", 0.0)))
        bottom = max(float(first_point.get("y", 0.0)), float(second_point.get("y", 0.0)))

        new_x = float(point.get("x", left))
        new_y = float(point.get("y", top))
        if corner_index == 0:  # top-left
            left = new_x
            top = new_y
        elif corner_index == 1:  # bottom-right
            right = new_x
            bottom = new_y
        elif corner_index == 2:  # top-right
            right = new_x
            top = new_y
        else:  # bottom-left
            left = new_x
            bottom = new_y

        left, right = sorted((left, right))
        top, bottom = sorted((top, bottom))
        self._task_current_draft_points = [
            {"x": round(left, 4), "y": round(top, 4)},
            {"x": round(right, 4), "y": round(bottom, 4)},
        ]

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
                    show_bbox_handles=selected_annotation.label_type == "Bounding box",
                )

        draft_definition = self._build_task_annotation_definition()
        if draft_definition is not None:
            self._draw_task_annotation_shape(
                draft_definition,
                "#ef4444",
                show_indexes=True,
                selected_point_index=self._task_selected_draft_point_index,
                show_bbox_handles=draft_definition.get("type") == "Bounding box",
            )

    def _render_task_annotation_canvas(self) -> None:
        if self._task_annotation_canvas is None:
            return
        canvas = self._task_annotation_canvas
        canvas_focus = self._task_pending_canvas_focus or self._default_task_canvas_focus()
        self._task_pending_canvas_focus = None
        canvas.delete("task_message")
        self._task_image_render_box = None
        canvas.update_idletasks()
        viewport_width = float(canvas.winfo_width())
        viewport_height = float(canvas.winfo_height())
        if viewport_width <= 1.0:
            viewport_width = float(self.TASK_CANVAS_WIDTH)
        if viewport_height <= 1.0:
            viewport_height = float(self.TASK_CANVAS_HEIGHT)
        canvas.configure(scrollregion=(0, 0, viewport_width, viewport_height))

        image_path = self._task_current_image_path
        if image_path and Path(image_path).exists() and Image is not None and ImageTk is not None and ImageOps is not None:
            if self._task_source_image_path != image_path or self._task_source_image is None:
                self._task_source_image = Image.open(image_path)
                self._task_source_image_path = image_path
            image = ImageOps.contain(
                self._task_source_image,
                (
                    max(1, round(viewport_width * self._task_image_zoom)),
                    max(1, round(viewport_height * self._task_image_zoom)),
                ),
            )
            photo = ImageTk.PhotoImage(image)
            self._task_image_photo = photo
            pending_zoom_anchor = self._task_pending_zoom_canvas_anchor
            if pending_zoom_anchor is not None:
                local_x, local_y, anchor_canvas_x, anchor_canvas_y = pending_zoom_anchor
                left = anchor_canvas_x - local_x * image.width
                top = anchor_canvas_y - local_y * image.height
            else:
                left = max(0.0, (viewport_width - image.width) / 2)
                top = max(0.0, (viewport_height - image.height) / 2)
            right = left + image.width
            bottom = top + image.height
            self._task_image_render_box = (left, top, right, bottom)
            canvas.configure(
                scrollregion=(
                    min(0.0, left),
                    min(0.0, top),
                    max(viewport_width, right),
                    max(viewport_height, bottom),
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
            self._task_source_image = None
            self._task_source_image_path = None
            if self._task_annotation_image_item is not None:
                canvas.delete(self._task_annotation_image_item)
                self._task_annotation_image_item = None
            canvas.create_text(
                viewport_width / 2,
                viewport_height / 2,
                text="Brak obrazu do annotacji",
                fill="#e5e7eb",
                tags=("task_message",),
            )
            return

        self._render_task_annotation_overlay()
        if self._task_pending_zoom_canvas_anchor is not None:
            _local_x, _local_y, _anchor_canvas_x, _anchor_canvas_y = self._task_pending_zoom_canvas_anchor
            self._task_pending_zoom_canvas_anchor = None
        else:
            self._restore_task_canvas_focus(canvas_focus)

    def _move_task_canvas_to_anchor(
        self,
        target_canvas_x: float,
        target_canvas_y: float,
        viewport_x: float,
        viewport_y: float,
    ) -> None:
        if self._task_annotation_canvas is None:
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

        target_left = target_canvas_x - viewport_x
        target_top = target_canvas_y - viewport_y

        if region_width <= viewport_width:
            canvas.xview_moveto(0.0)
        else:
            x_fraction = (target_left - region_left) / max(1.0, region_width - viewport_width)
            canvas.xview_moveto(min(1.0, max(0.0, x_fraction)))

        if region_height <= viewport_height:
            canvas.yview_moveto(0.0)
        else:
            y_fraction = (target_top - region_top) / max(1.0, region_height - viewport_height)
            canvas.yview_moveto(min(1.0, max(0.0, y_fraction)))

    def _draw_task_annotation_shape(
        self,
        annotation_definition: dict[str, object],
        color: str,
        show_indexes: bool = False,
        selected_point_index: int | None = None,
        show_bbox_handles: bool = False,
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
                left, right = sorted((x0, x1))
                top, bottom = sorted((y0, y1))
                self._task_annotation_canvas.create_rectangle(
                    left,
                    top,
                    right,
                    bottom,
                    outline=color,
                    width=2,
                    tags=("annotation_overlay",),
                )
                if show_bbox_handles:
                    corners = [(left, top), (right, bottom), (right, top), (left, bottom)]
                    for corner_index, (corner_x, corner_y) in enumerate(corners):
                        radius = 7 if selected_point_index == corner_index else 5
                        outline = "#fde68a" if selected_point_index == corner_index else "#ffffff"
                        self._task_annotation_canvas.create_oval(
                            corner_x - radius,
                            corner_y - radius,
                            corner_x + radius,
                            corner_y + radius,
                            fill=color,
                            outline=outline,
                            width=2 if selected_point_index == corner_index else 1,
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
        if self._task_syncing_tree_selection:
            return
        selected = tree.selection()
        annotation_id = self.annotation_ids_by_row.get(selected[0]) if selected else None
        self._task_selected_annotation_id = annotation_id
        if annotation_id is None:
            self._render_task_annotation_overlay()
            return
        self._start_annotation_edit(annotation_id)

    def _start_selected_annotation_reposition(self) -> None:
        tree = self._task_annotations_tree
        if tree is None:
            return
        selected = tree.selection()
        if not selected:
            if self._task_status_var is not None:
                self._task_status_var.set("Najpierw wybierz zapisany label z listy po prawej stronie.")
            return

        annotation_id = self.annotation_ids_by_row.get(selected[0])
        if annotation_id is None:
            return

        self._start_annotation_edit(annotation_id)

    def _start_annotation_edit(self, annotation_id: int) -> None:
        annotation = self._task_annotations_by_id.get(annotation_id)
        if annotation is None or annotation.annotation_definition is None:
            if self._task_status_var is not None:
                self._task_status_var.set("Wybrana annotacja nie ma zapisanej geometrii do edycji.")
            return
        if annotation.label_template_id is None:
            if self._task_status_var is not None:
                self._task_status_var.set("Nie mozna edytowac tej annotacji bez powiazanej etykiety.")
            return

        self._task_selected_annotation_id = annotation_id
        self._select_annotation_by_id(annotation_id)

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
        self._task_dragging_new_bbox = False
        self._task_dragging_annotation_body = False
        self._task_drag_last_canvas_point = None
        self._refresh_task_submit_button()
        self._render_task_annotation_overlay()
        if self._task_status_var is not None:
            self._task_status_var.set("Tryb edycji aktywny. Przesuwaj punkty/rogi, aby zmieniac polozenie i rozmiar, a potem kliknij 'Zapisz polozenie keypointow'.")

    def _delete_selected_annotation(self, _event: tk.Event | None = None) -> str | None:
        if not self._delete_annotation_callback:
            return None
        tree = self._task_annotations_tree
        if tree is None:
            return None
        selected = tree.selection()
        if not selected:
            return None
        annotation_id = self.annotation_ids_by_row.get(selected[0])
        if annotation_id is not None:
            self._delete_annotation_callback(annotation_id)
            return "break"
        return None

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
        self.bind("<Delete>", self._delete_selected_annotation)
        self.bind("<c>", self._shortcut_clear_draft)
        self.bind("<C>", self._shortcut_clear_draft)
        self.bind("<v>", self._shortcut_copy_previous)
        self.bind("<V>", self._shortcut_copy_previous)
        self.bind("<n>", self._shortcut_submit_annotation)
        self.bind("<N>", self._shortcut_submit_annotation)

    def _shortcut_clear_draft(self, _event: tk.Event | None = None) -> str | None:
        if self._task_annotation_canvas is None:
            return None
        self._clear_task_annotation_draft()
        return "break"

    def _shortcut_copy_previous(self, _event: tk.Event | None = None) -> str | None:
        if self._task_annotation_canvas is None:
            return None
        self._copy_task_annotation_from_previous_image()
        return "break"

    def _shortcut_submit_annotation(self, _event: tk.Event | None = None) -> str | None:
        if self._task_annotation_canvas is None:
            return None
        self._request_task_submit()
        return "break"

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
        self.unbind("<Delete>")
        self.unbind("<c>")
        self.unbind("<C>")
        self.unbind("<v>")
        self.unbind("<V>")
        self.unbind("<n>")
        self.unbind("<N>")
        if self._task_label_picker is not None and self._task_label_picker.winfo_exists():
            self._task_label_picker.destroy()
        self._task_label_picker = None
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
        self._task_dragging_new_bbox = False
        self._task_image_render_box = None
        self._task_image_photo = None
        self._task_source_image = None
        self._task_source_image_path = None
        self._task_annotation_image_item = None
        self._task_pending_canvas_focus = None
        self._task_pending_zoom_canvas_anchor = None
        self._task_status_var = None
        self._task_template_info_var = None
        self._task_template_preview_holder = None
        self._task_annotation_canvas = None
        self._task_annotations_tree = None
        self._task_submit_button = None
        self._task_page_frame = None
        self._task_page_task_id = None
        self._task_page_project_id = None
        self._task_header_label = None
        self._task_counter_label = None
        self._task_image_name_label = None
        self._task_pan_start = None
        self._task_is_panning = False
        self._task_dragging_annotation_body = False
        self._task_drag_last_canvas_point = None
        self._task_tooltips = []
        frame = ttk.Frame(self.content)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        return frame

    def _on_task_pan_start(self, event: tk.Event) -> None:
        if self._task_annotation_canvas is None:
            return
        self._task_pan_start = (float(event.x), float(event.y))
        self._task_annotation_canvas.scan_mark(int(event.x), int(event.y))
        self._task_is_panning = True

    def _on_task_pan_drag(self, event: tk.Event) -> None:
        if self._task_annotation_canvas is None or not self._task_is_panning:
            return
        self._task_annotation_canvas.scan_dragto(int(event.x), int(event.y), gain=1)

    def _on_task_pan_end(self, _event: tk.Event) -> None:
        self._task_is_panning = False
        self._task_pan_start = None

    def _select_annotation_by_id(self, annotation_id: int) -> None:
        self._task_selected_annotation_id = annotation_id
        tree = self._task_annotations_tree
        if tree is None:
            self._render_task_annotation_overlay()
            return
        for row_id, row_annotation_id in self.annotation_ids_by_row.items():
            if row_annotation_id == annotation_id:
                current_selection = tree.selection()
                if not current_selection or current_selection[0] != row_id:
                    self._task_syncing_tree_selection = True
                    tree.selection_set(row_id)
                    self._task_syncing_tree_selection = False
                tree.focus(row_id)
                tree.see(row_id)
                break
        self._render_task_annotation_overlay()

    def _label_type_short_name(self, label_type: str) -> str:
        mapping = {
            "Bounding box": "B",
            "Segmentacja (maska)": "M",
            "Skeleton": "S",
            "Polygon": "P",
            "Point": "Pt",
            "Polyline": "L",
            "Klasyfikacja": "K",
        }
        return mapping.get(label_type, "?")

    def _find_annotation_at_canvas_point(self, canvas_x: float, canvas_y: float) -> int | None:
        if self._task_image_render_box is None:
            return None
        point_radius = 10.0
        line_radius = 8.0

        for annotation in reversed(self._task_current_annotations):
            definition = annotation.annotation_definition
            if definition is None:
                continue
            points = definition.get("points", [])
            if not isinstance(points, list) or not points:
                continue
            canvas_points = [
                self._to_task_canvas_point(point)
                for point in points
                if isinstance(point, dict) and "x" in point and "y" in point
            ]
            if not canvas_points:
                continue

            if any((point_x - canvas_x) ** 2 + (point_y - canvas_y) ** 2 <= point_radius**2 for point_x, point_y in canvas_points):
                return annotation.id

            shape_type = str(definition.get("type") or annotation.label_type)
            if shape_type == "Bounding box" and len(canvas_points) >= 2:
                (x0, y0), (x1, y1) = canvas_points[:2]
                left, right = sorted((x0, x1))
                top, bottom = sorted((y0, y1))
                if left <= canvas_x <= right and top <= canvas_y <= bottom:
                    return annotation.id
                continue

            if shape_type in {"Polyline", "Skeleton", "Polygon", "Segmentacja (maska)"} and len(canvas_points) >= 2:
                if self._is_point_close_to_polyline(canvas_x, canvas_y, canvas_points, line_radius):
                    return annotation.id
                if shape_type in {"Polygon", "Segmentacja (maska)"} and len(canvas_points) >= 3:
                    if self._is_point_inside_polygon(canvas_x, canvas_y, canvas_points):
                        return annotation.id
        return None

    def _is_point_close_to_polyline(
        self,
        x_pos: float,
        y_pos: float,
        polyline_points: list[tuple[float, float]],
        tolerance: float,
    ) -> bool:
        if len(polyline_points) < 2:
            return False
        for index in range(len(polyline_points) - 1):
            if self._distance_point_to_segment(x_pos, y_pos, polyline_points[index], polyline_points[index + 1]) <= tolerance:
                return True
        return False

    def _distance_point_to_segment(
        self,
        x_pos: float,
        y_pos: float,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> float:
        x1, y1 = start
        x2, y2 = end
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return ((x_pos - x1) ** 2 + (y_pos - y1) ** 2) ** 0.5
        projection = ((x_pos - x1) * dx + (y_pos - y1) * dy) / (dx * dx + dy * dy)
        clamped_projection = min(1.0, max(0.0, projection))
        closest_x = x1 + clamped_projection * dx
        closest_y = y1 + clamped_projection * dy
        return ((x_pos - closest_x) ** 2 + (y_pos - closest_y) ** 2) ** 0.5

    def _is_point_inside_polygon(self, x_pos: float, y_pos: float, polygon_points: list[tuple[float, float]]) -> bool:
        inside = False
        point_count = len(polygon_points)
        if point_count < 3:
            return False
        previous_index = point_count - 1
        for current_index in range(point_count):
            x_current, y_current = polygon_points[current_index]
            x_previous, y_previous = polygon_points[previous_index]
            intersects = (y_current > y_pos) != (y_previous > y_pos)
            if intersects:
                cross_x = (x_previous - x_current) * (y_pos - y_current) / max(1e-9, (y_previous - y_current)) + x_current
                if x_pos < cross_x:
                    inside = not inside
            previous_index = current_index
        return inside

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