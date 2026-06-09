from __future__ import annotations

from pathlib import Path
from tkinter import messagebox

from database.repositories import AppRepository
from database.sqlite_db import DatabaseManager
from gui.app_view import AppView
from gui.dialogs import (
    CreateProjectDialog,
    CreateTaskDialog,
    ExportDialog,
    MergeDialog,
)
from model.entities import LabelTemplate, SessionState
from model.services import AppService


class AppController:
    def __init__(self) -> None:
        root_dir = Path(__file__).resolve().parent.parent
        database_path = root_dir / "database" / "annotatio.sqlite"

        self.database = DatabaseManager(database_path)
        self.repository = AppRepository(self.database)
        self.service = AppService(self.repository)
        self.view = AppView()

        self.current_page = "home"
        self.current_project_id: int | None = None
        self.current_task_id: int | None = None
        self.current_image_index = 0

        self._bind_callbacks()

    def _bind_callbacks(self) -> None:
        self.view.set_navigation_callback(self.open_page)
        self.view.set_create_project_callback(self.open_create_project_dialog)
        self.view.set_export_project_callback(self.open_export_dialog)
        self.view.set_open_project_callback(self.open_project)
        self.view.set_back_to_projects_callback(self.show_projects_page)
        self.view.set_create_task_callback(self.open_create_task_dialog)
        self.view.set_open_task_callback(self.open_task)
        self.view.set_merge_projects_callback(self.open_merge_projects_dialog)
        self.view.set_merge_tasks_callback(self.open_merge_tasks_dialog)
        self.view.set_add_annotation_callback(self.add_annotation)
        self.view.set_toggle_annotation_callback(self.toggle_annotation_visibility)
        self.view.set_delete_annotation_callback(self.delete_annotation)
        self.view.set_delete_image_callback(self.delete_current_image)
        self.view.set_auto_label_callback(self.auto_label_current_image)
        self.view.set_change_image_callback(self.change_image)
        self.view.set_close_callback(self.on_close)

    def run(self) -> None:
        session = self.service.load_session_state()
        self.view.apply_session_state(session)

        if session.last_page == "task" and session.last_task_id:
            self.open_task(session.last_task_id)
        elif session.last_page == "project" and session.last_project_id:
            self.open_project(session.last_project_id)
        elif session.last_page == "projects":
            self.show_projects_page()
        elif session.last_page == "settings":
            self.show_settings_page()
        elif session.last_page == "info":
            self.show_info_page()
        else:
            self.show_start_page()

        self.view.mainloop()

    def open_page(self, page_name: str) -> None:
        routing = {
            "home": self.show_start_page,
            "projects": self.show_projects_page,
            "settings": self.show_settings_page,
            "info": self.show_info_page,
        }
        action = routing.get(page_name)
        if action:
            action()

    def show_start_page(self) -> None:
        self.current_page = "home"
        self.current_project_id = None
        self.current_task_id = None
        self.current_image_index = 0
        self.view.show_start_page(self.service.get_start_description())

    def show_projects_page(self) -> None:
        self.current_page = "projects"
        self.current_project_id = None
        self.current_task_id = None
        self.current_image_index = 0
        self.view.show_projects_page(self.service.list_projects())

    def show_settings_page(self) -> None:
        self.current_page = "settings"
        self.view.show_settings_page(self.service.get_settings_description())

    def show_info_page(self) -> None:
        self.current_page = "info"
        self.view.show_info_page(self.service.get_info_description())

    def open_create_project_dialog(self) -> None:
        dialog = CreateProjectDialog(self.view)
        payload = dialog.show()
        if not payload:
            return

        labels = [
            LabelTemplate(
                id=None,
                name=item["name"],
                label_type=item["label_type"],
                preview_image_path=item["preview_image_path"],
            )
            for item in payload["labels"]
        ]

        try:
            project_id = self.service.create_project(
                payload["name"],
                payload["project_type"],
                labels,
            )
        except ValueError as error:
            messagebox.showerror("Blad walidacji", str(error), parent=self.view)
            return

        self.open_project(project_id)

    def open_export_dialog(self) -> None:
        project_id = self.current_project_id
        if project_id is None:
            project_id = self.view.get_selected_project_id()

        if project_id is None:
            messagebox.showinfo("Eksport", "Najpierw wybierz projekt.", parent=self.view)
            return

        dialog = ExportDialog(self.view)
        payload = dialog.show()
        if not payload:
            return

        try:
            export_dir = self.service.export_project(
                project_id=project_id,
                export_format=payload["export_format"],
                split=payload["split"],
                include_images=payload["include_images"],
                destination_folder=payload["destination_folder"],
            )
        except ValueError as error:
            messagebox.showerror("Eksport", str(error), parent=self.view)
            return

        messagebox.showinfo(
            "Eksport zakonczony",
            f"Dane zostaly zapisane do:\n{export_dir}",
            parent=self.view,
        )

    def open_project(self, project_id: int) -> None:
        try:
            project = self.service.get_project(project_id)
        except ValueError as error:
            messagebox.showerror("Projekt", str(error), parent=self.view)
            self.show_projects_page()
            return

        self.current_page = "project"
        self.current_project_id = project_id
        self.current_task_id = None
        self.current_image_index = 0
        self.view.show_project_page(project, self.service.list_tasks(project_id))

    def open_create_task_dialog(self) -> None:
        if self.current_project_id is None:
            return

        dialog = CreateTaskDialog(self.view)
        payload = dialog.show()
        if not payload:
            return

        try:
            self.service.create_task(
                project_id=self.current_project_id,
                task_name=payload["task_name"],
                dataset_folder=payload["dataset_folder"],
            )
        except ValueError as error:
            messagebox.showerror("Task", str(error), parent=self.view)
            return

        self.open_project(self.current_project_id)

    def open_merge_projects_dialog(self) -> None:
        projects = self.service.list_projects()
        if len(projects) < 2:
            messagebox.showinfo(
                "Scalanie projektow",
                "Potrzebujesz co najmniej dwoch projektow.",
                parent=self.view,
            )
            return

        dialog = MergeDialog(
            self.view,
            title="Merge Projects",
            source_label="Projekt zrodlowy",
            target_label="Projekt docelowy",
            options=[(item.id, item.name) for item in projects],
        )
        payload = dialog.show()
        if not payload:
            return

        try:
            self.service.merge_projects(payload["source_id"], payload["target_id"])
        except ValueError as error:
            messagebox.showerror("Scalanie projektow", str(error), parent=self.view)
            return

        self.show_projects_page()

    def open_merge_tasks_dialog(self) -> None:
        if self.current_project_id is None:
            return

        tasks = self.service.list_tasks(self.current_project_id)
        if len(tasks) < 2:
            messagebox.showinfo(
                "Scalanie taskow",
                "Potrzebujesz co najmniej dwoch taskow w projekcie.",
                parent=self.view,
            )
            return

        dialog = MergeDialog(
            self.view,
            title="Merge Tasks",
            source_label="Task zrodlowy",
            target_label="Task docelowy",
            options=[(item.id, item.name) for item in tasks],
        )
        payload = dialog.show()
        if not payload:
            return

        try:
            self.service.merge_tasks(payload["source_id"], payload["target_id"])
        except ValueError as error:
            messagebox.showerror("Scalanie taskow", str(error), parent=self.view)
            return

        self.open_project(self.current_project_id)

    def open_task(self, task_id: int) -> None:
        try:
            workspace = self.service.get_task_workspace(task_id)
        except ValueError as error:
            messagebox.showerror("Task", str(error), parent=self.view)
            if self.current_project_id:
                self.open_project(self.current_project_id)
            return

        self.current_page = "task"
        self.current_project_id = workspace["project"].id
        self.current_task_id = task_id
        images = workspace["images"]
        if images:
            self.current_image_index = max(0, min(self.current_image_index, len(images) - 1))
        else:
            self.current_image_index = 0

        self.view.show_task_page(workspace, self.current_image_index)

    def change_image(self, step: int) -> None:
        if self.current_task_id is None:
            return

        workspace = self.service.get_task_workspace(self.current_task_id)
        images = workspace["images"]
        if not images:
            self.current_image_index = 0
        else:
            self.current_image_index = (self.current_image_index + step) % len(images)
        self.view.show_task_page(workspace, self.current_image_index)

    def add_annotation(self, label_template_id: int, note: str) -> None:
        if self.current_task_id is None:
            return

        workspace = self.service.get_task_workspace(self.current_task_id)
        images = workspace["images"]
        if not images:
            messagebox.showinfo("Adnotacje", "Ten task nie ma obrazow.", parent=self.view)
            return

        image_id = images[self.current_image_index].id
        try:
            self.service.add_annotation(image_id, label_template_id, note)
        except ValueError as error:
            messagebox.showerror("Adnotacje", str(error), parent=self.view)
            return

        self.open_task(self.current_task_id)

    def toggle_annotation_visibility(self, annotation_id: int) -> None:
        if self.current_task_id is None:
            return
        self.service.toggle_annotation_visibility(annotation_id)
        self.open_task(self.current_task_id)

    def delete_annotation(self, annotation_id: int) -> None:
        if self.current_task_id is None:
            return
        self.service.delete_annotation(annotation_id)
        self.open_task(self.current_task_id)

    def delete_current_image(self) -> None:
        if self.current_task_id is None:
            return

        workspace = self.service.get_task_workspace(self.current_task_id)
        images = workspace["images"]
        if not images:
            return

        image_id = images[self.current_image_index].id
        self.service.delete_image(image_id)
        self.current_image_index = max(0, self.current_image_index - 1)
        self.open_task(self.current_task_id)

    def auto_label_current_image(self) -> None:
        if self.current_task_id is None:
            return

        workspace = self.service.get_task_workspace(self.current_task_id)
        images = workspace["images"]
        if not images:
            messagebox.showinfo("Model", "Brak obrazow do oznaczenia.", parent=self.view)
            return

        image_id = images[self.current_image_index].id
        try:
            self.service.auto_label_image(image_id)
        except ValueError as error:
            messagebox.showerror("Model", str(error), parent=self.view)
            return

        self.open_task(self.current_task_id)

    def on_close(self) -> None:
        width = self.view.winfo_width() or 1400
        height = self.view.winfo_height() or 900
        session = SessionState(
            last_page=self.current_page,
            last_project_id=self.current_project_id,
            last_task_id=self.current_task_id,
            window_width=width,
            window_height=height,
        )
        self.service.save_session_state(session)
        self.view.destroy()