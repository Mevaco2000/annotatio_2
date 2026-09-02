from __future__ import annotations

from pathlib import Path
from queue import Empty, Queue
import threading
from tkinter import messagebox

from database.repositories import AppRepository
from database.sqlite_db import DatabaseManager
from gui.app_view import AppView
from gui.dialogs import (
    BatchProgressDialog,
    CreateProjectDialog,
    CreateTaskDialog,
    ExportDialog,
    ImportDatasetDialog,
    MergeProjectsDialog,
    ImportTypeFilterDialog,
    MergeDialog,
    ModelInferenceDialog,
)
from model.entities import LabelTemplate, SessionState
from model.labels_checks_service import LabelsChecksService
from model.services import AppService


class AppController:
    def __init__(self) -> None:
        self.root_dir = Path(__file__).resolve().parent.parent
        database_path = self.root_dir / "database" / "annotatio.sqlite"

        self.database = DatabaseManager(database_path)
        self.repository = AppRepository(self.database)
        self.service = AppService(self.repository, self.root_dir / "projects")
        self.labels_checks_service = LabelsChecksService()
        self.view = AppView()

        self.current_page = "home"
        self.current_project_id: int | None = None
        self.current_task_id: int | None = None
        self.current_image_index = 0
        self._task_workspace_cache: dict | None = None
        self.session_state = SessionState()

        self._bind_callbacks()

    def _get_task_workspace(self, task_id: int, force_reload: bool = False) -> dict:
        if not force_reload and self.current_task_id == task_id and self._task_workspace_cache is not None:
            return self._task_workspace_cache
        workspace = self.service.get_task_workspace(task_id)
        self._task_workspace_cache = workspace
        return workspace

    def _invalidate_task_workspace_cache(self) -> None:
        self._task_workspace_cache = None

    def _bind_callbacks(self) -> None:
        self.view.set_navigation_callback(self.open_page)
        self.view.set_create_project_callback(self.open_create_project_dialog)
        self.view.set_export_project_callback(self.open_export_dialog)
        self.view.set_import_dataset_callback(self.open_import_dataset_dialog)
        self.view.set_open_project_callback(self.open_project)
        self.view.set_back_to_projects_callback(self.show_projects_page)
        self.view.set_create_task_callback(self.open_create_task_dialog)
        self.view.set_open_task_callback(self.open_task)
        self.view.set_delete_project_callback(self.delete_project)
        self.view.set_delete_task_callback(self.delete_task)
        self.view.set_merge_projects_callback(self.open_merge_projects_dialog)
        self.view.set_merge_tasks_callback(self.open_merge_tasks_dialog)
        self.view.set_add_annotation_callback(self.add_annotation)
        self.view.set_update_annotation_callback(self.update_annotation)
        self.view.set_toggle_annotation_callback(self.toggle_annotation_visibility)
        self.view.set_delete_annotation_callback(self.delete_annotation)
        self.view.set_delete_image_callback(self.delete_current_image)
        self.view.set_auto_label_callback(self.auto_label_current_image)
        self.view.set_auto_label_task_callback(self.auto_label_task_images)
        self.view.set_run_last_model_callback(self.run_last_model_for_current_image)
        self.view.set_copy_previous_annotation_callback(self.copy_annotation_from_previous_image)
        self.view.set_change_image_callback(self.change_image)
        self.view.set_close_callback(self.on_close)

    def _run_dataset_import_with_progress(self, action):
        progress_dialog = BatchProgressDialog(self.view, "Import Dataset", 1)
        progress_dialog.status_var.set("Trwa import datasetu. To moze potrwac chwile...")
        progress_dialog.counter_var.set("0 / 1")
        progress_dialog.details_var.set("Zaimportowane annotacje: 0")
        progress_dialog.set_indeterminate(True)
        progress_dialog._refresh()
        event_queue: Queue = Queue()
        state: dict[str, object] = {"done": False, "result": None, "error": None, "last_annotations": 0}

        def on_progress(completed_images: int, total_images: int, current_image_name: str, imported_annotations: int) -> None:
            event_queue.put(("progress", int(completed_images), int(total_images), current_image_name, int(imported_annotations)))

        def worker() -> None:
            try:
                result = action(on_progress)
                event_queue.put(("done", result))
            except Exception as error:
                event_queue.put(("error", error))

        def poll_queue() -> None:
            while True:
                try:
                    event = event_queue.get_nowait()
                except Empty:
                    break

                event_type = event[0]
                if event_type == "progress":
                    _, completed_images, total_images, current_image_name, imported_annotations = event
                    safe_total = max(1, int(total_images))
                    bounded_completed = max(0, min(int(completed_images), safe_total))
                    progress_dialog.set_indeterminate(False)
                    progress_dialog.progress.configure(maximum=safe_total, value=bounded_completed)
                    progress_dialog.counter_var.set(f"{int(completed_images)} / {int(total_images)}")
                    if current_image_name:
                        progress_dialog.status_var.set(f"Import obrazu {int(completed_images)}/{int(total_images)}: {current_image_name}")
                    else:
                        progress_dialog.status_var.set("Trwa import datasetu. To moze potrwac chwile...")
                    progress_dialog.details_var.set(f"Zaimportowane annotacje: {int(imported_annotations)}")
                    state["last_annotations"] = int(imported_annotations)
                    progress_dialog._refresh()
                elif event_type == "done":
                    state["done"] = True
                    state["result"] = event[1]
                elif event_type == "error":
                    state["done"] = True
                    state["error"] = event[1]

            if bool(state["done"]):
                progress_dialog.set_indeterminate(False)
                progress_dialog.status_var.set("Import zakonczony")
                progress_dialog.details_var.set(f"Zaimportowane annotacje: {int(state['last_annotations'])}")
                progress_dialog._refresh()
                if progress_dialog.winfo_exists():
                    progress_dialog.close()
                return

            if progress_dialog.winfo_exists():
                self.view.after(50, poll_queue)

        threading.Thread(target=worker, daemon=True).start()
        self.view.after(0, poll_queue)
        progress_dialog.wait_window(progress_dialog)
        if state["error"] is not None:
            raise state["error"]
        return state["result"]

    def _run_video_import_with_progress(self, action):
        progress_dialog = BatchProgressDialog(self.view, "Import klatek z wideo", 1)
        progress_dialog.status_var.set("Trwa import klatek. To moze potrwac chwile...")
        progress_dialog.counter_var.set("0 / 1")
        progress_dialog.details_var.set("Zaimportowane klatki: 0")
        progress_dialog.set_indeterminate(True)
        progress_dialog._refresh()

        event_queue: Queue = Queue()
        state: dict[str, object] = {"done": False, "result": None, "error": None, "last_completed": 0, "last_total": 1}

        def on_progress(completed_images: int, total_images: int, current_image_name: str, _imported_annotations: int) -> None:
            event_queue.put(("progress", int(completed_images), int(total_images), current_image_name))

        def worker() -> None:
            try:
                result = action(on_progress)
                event_queue.put(("done", result))
            except Exception as error:
                event_queue.put(("error", error))

        def poll_queue() -> None:
            while True:
                try:
                    event = event_queue.get_nowait()
                except Empty:
                    break

                event_type = event[0]
                if event_type == "progress":
                    _, completed_frames, total_frames, current_name = event
                    safe_total = max(1, int(total_frames))
                    bounded_completed = max(0, min(int(completed_frames), safe_total))
                    progress_dialog.set_indeterminate(False)
                    progress_dialog.progress.configure(maximum=safe_total, value=bounded_completed)
                    progress_dialog.counter_var.set(f"{int(completed_frames)} / {int(total_frames)}")
                    if current_name:
                        progress_dialog.status_var.set(
                            f"Import klatki {int(completed_frames)}/{int(total_frames)}: {current_name}"
                        )
                    else:
                        progress_dialog.status_var.set("Trwa import klatek. To moze potrwac chwile...")
                    progress_dialog.details_var.set(f"Zaimportowane klatki: {bounded_completed}")
                    progress_dialog._refresh()
                    state["last_completed"] = bounded_completed
                    state["last_total"] = safe_total
                elif event_type == "done":
                    state["done"] = True
                    state["result"] = event[1]
                elif event_type == "error":
                    state["done"] = True
                    state["error"] = event[1]

            if bool(state["done"]):
                progress_dialog.set_indeterminate(False)
                progress_dialog.status_var.set("Import klatek zakonczony")
                progress_dialog.counter_var.set(f"{int(state['last_completed'])} / {int(state['last_total'])}")
                progress_dialog.details_var.set(f"Zaimportowane klatki: {int(state['last_completed'])}")
                progress_dialog._refresh()
                if progress_dialog.winfo_exists():
                    progress_dialog.close()
                return

            if progress_dialog.winfo_exists():
                self.view.after(50, poll_queue)

        threading.Thread(target=worker, daemon=True).start()
        self.view.after(0, poll_queue)
        progress_dialog.wait_window(progress_dialog)
        if state["error"] is not None:
            raise state["error"]
        return state["result"]

    def _resolve_allowed_label_types(self, dataset_folder: str, dataset_format: str) -> list[str] | None:
        detected_types = self.service.detect_dataset_annotation_types(dataset_folder, dataset_format)
        if len(detected_types) <= 1:
            return detected_types or None

        dialog = ImportTypeFilterDialog(self.view, detected_types)
        payload = dialog.show()
        if not payload:
            return []
        selected = [label_type for label_type in payload.get("allowed_label_types", []) if isinstance(label_type, str)]
        return selected

    def run(self) -> None:
        self.session_state = self.service.load_session_state()
        self.view.apply_session_state(self.session_state)

        if self.session_state.last_page == "task" and self.session_state.last_task_id:
            self.open_task(self.session_state.last_task_id)
        elif self.session_state.last_page == "project" and self.session_state.last_project_id:
            self.open_project(self.session_state.last_project_id)
        elif self.session_state.last_page == "projects":
            self.show_projects_page()
        elif self.session_state.last_page == "settings":
            self.show_settings_page()
        elif self.session_state.last_page == "labels-checks":
            self.show_labels_checks_page()
        elif self.session_state.last_page == "info":
            self.show_info_page()
        else:
            self.show_start_page()

        self.view.mainloop()

    def _build_session_state(self) -> SessionState:
        width = self.view.winfo_width() or self.session_state.window_width or 1400
        height = self.view.winfo_height() or self.session_state.window_height or 900
        return SessionState(
            last_page=self.current_page,
            last_project_id=self.current_project_id,
            last_task_id=self.current_task_id,
            window_width=width,
            window_height=height,
            last_model_config=self.session_state.last_model_config,
            last_task_dialog_config=self.session_state.last_task_dialog_config,
        )

    def _save_session_state(self) -> None:
        self.session_state = self._build_session_state()
        self.service.save_session_state(self.session_state)

    def _get_last_model_config_for_modes(self, available_modes: list[str]) -> dict[str, object] | None:
        saved_config = self.session_state.last_model_config
        if not isinstance(saved_config, dict):
            return None
        payload = dict(saved_config)
        if available_modes:
            saved_mode = str(payload.get("mode") or "").strip()
            if saved_mode not in available_modes:
                payload["mode"] = available_modes[0]
        return payload

    def _get_auto_label_context(self) -> tuple[dict, list, list[str]] | None:
        if self.current_task_id is None:
            return None

        workspace = self._get_task_workspace(self.current_task_id)
        images = workspace["images"]
        if not images:
            messagebox.showinfo("Model", "Brak obrazow do oznaczenia.", parent=self.view)
            return None

        available_modes = self.service.get_available_model_inference_modes(
            workspace["project"].project_type,
            workspace["labels"],
        )
        if not available_modes:
            messagebox.showinfo(
                "Model",
                "Dla tego projektu obslugiwane sa tylko zgodne tryby modelowe zalezne od typu etykiet: klasyfikacja, detekcja obiektow, pose albo segmentacja.",
                parent=self.view,
            )
            return None

        return workspace, images, available_modes

    def _run_auto_label_payload(
        self,
        workspace: dict,
        images: list,
        payload: dict[str, object],
        save_as_last_used: bool = True,
        target_image_indexes: list[int] | None = None,
    ) -> None:
        if save_as_last_used:
            self.session_state.last_model_config = dict(payload)
            self._save_session_state()

        indexes = list(target_image_indexes) if target_image_indexes is not None else [self.current_image_index]
        total_added_count = 0
        progress_dialog = BatchProgressDialog(self.view, "Autolabeling taska", len(indexes)) if len(indexes) > 1 else None
        try:
            for progress_index, image_index in enumerate(indexes, start=1):
                image_record = images[image_index]
                image_name = Path(image_record.file_path).name
                try:
                    total_added_count += self.service.auto_label_image(
                        image_id=image_record.id,
                        image_path=image_record.file_path,
                        project_type=workspace["project"].project_type,
                        project_labels=workspace["labels"],
                        config=payload,
                    )
                    if progress_dialog is not None:
                        progress_dialog.update_progress(progress_index, image_name, total_added_count)
                except ValueError as error:
                    if progress_dialog is not None:
                        progress_dialog.close()
                    if len(indexes) == 1:
                        messagebox.showerror("Model", str(error), parent=self.view)
                    else:
                        messagebox.showerror(
                            "Model",
                            f"Autolabeling taska zostal przerwany na obrazie {progress_index}/{len(indexes)} ({image_name}). Dodano dotad {total_added_count} annotacji.\n\n{error}",
                            parent=self.view,
                        )
                    return
        finally:
            if progress_dialog is not None and progress_dialog.winfo_exists():
                progress_dialog.close()

        self._get_task_workspace(self.current_task_id, force_reload=True)
        self.open_task(self.current_task_id)
        if len(indexes) == 1:
            messagebox.showinfo("Model", f"Dodano {total_added_count} annotacji z modelu.", parent=self.view)
            return
        messagebox.showinfo(
            "Model",
            f"Przetworzono {len(indexes)} obrazow i dodano {total_added_count} annotacji z modelu.",
            parent=self.view,
        )

    def open_page(self, page_name: str) -> None:
        routing = {
            "home": self.show_start_page,
            "projects": self.show_projects_page,
            "settings": self.show_settings_page,
            "labels-checks": self.show_labels_checks_page,
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
        self._invalidate_task_workspace_cache()
        self.view.show_start_page(self.service.get_start_description())

    def show_projects_page(self) -> None:
        self.current_page = "projects"
        self.current_project_id = None
        self.current_task_id = None
        self.current_image_index = 0
        self._invalidate_task_workspace_cache()
        self.view.show_projects_page(self.service.list_projects())

    def show_settings_page(self) -> None:
        self.current_page = "settings"
        self.view.show_settings_page(self.service.get_settings_description())

    def show_labels_checks_page(self) -> None:
        self.current_page = "labels-checks"
        self.view.show_labels_checks_page(self.labels_checks_service.get_description())

    def show_info_page(self) -> None:
        self.current_page = "info"
        self.view.show_info_page(self.service.get_info_description())

    def open_create_project_dialog(self) -> None:
        dialog = CreateProjectDialog(
            self.view,
            default_storage_folder=self.service.get_default_projects_root(),
        )
        payload = dialog.show()
        if not payload:
            return

        labels = [
            LabelTemplate(
                id=None,
                name=item["name"],
                label_type=item["label_type"],
                preview_image_path=item["preview_image_path"],
                preview_definition=item["preview_definition"],
            )
            for item in payload["labels"]
        ]

        try:
            project_id = self.service.create_project(
                payload["name"],
                payload["project_type"],
                labels,
                payload["storage_folder"],
            )
        except ValueError as error:
            messagebox.showerror("Blad walidacji", str(error), parent=self.view)
            return

        self.show_projects_page()

    def open_export_dialog(self) -> None:
        project_id = self.current_project_id
        if project_id is None:
            project_id = self.view.get_selected_project_id()

        if project_id is None:
            messagebox.showinfo("Eksport", "Najpierw wybierz projekt.", parent=self.view)
            return

        dialog = ExportDialog(self.view, self.service.get_available_export_formats(project_id))
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

    def open_import_dataset_dialog(self) -> None:
        project_id = self.current_project_id
        if project_id is None:
            project_id = self.view.get_selected_project_id()

        dialog = ImportDatasetDialog(self.view, self.service.DATASET_IMPORT_FORMATS)
        payload = dialog.show()
        if not payload:
            return

        dataset_folder = payload["dataset_folder"]
        dataset_format = payload["dataset_format"]
        default_task_name = Path(dataset_folder).name or "imported_task"
        task_name = str(payload.get("task_name") or "").strip() or default_task_name

        try:
            allowed_label_types = self._resolve_allowed_label_types(dataset_folder, dataset_format)
        except ValueError as error:
            messagebox.showerror("Import Dataset", str(error), parent=self.view)
            return
        if allowed_label_types == []:
            return

        if project_id is None:
            try:
                created_project_id, _task_id = self._run_dataset_import_with_progress(
                    lambda progress_callback: self.service.import_dataset_with_auto_project(
                        dataset_folder=dataset_folder,
                        dataset_format=dataset_format,
                        task_name=task_name,
                        project_name=Path(dataset_folder).name,
                        storage_folder=self.service.get_default_projects_root(),
                        allowed_label_types=allowed_label_types,
                        progress_callback=progress_callback,
                    )
                )
            except ValueError as error:
                messagebox.showerror("Import Dataset", str(error), parent=self.view)
                return

            report = self.service.pop_last_dataset_import_report() or {}
            skipped = int(report.get("skipped_missing_images", 0))
            self.open_project(created_project_id)
            message = "Dataset zostal zaimportowany. Utworzono nowy projekt i task automatycznie."
            if skipped > 0:
                message += f"\n\nPominieto {skipped} obrazow, bo nie znaleziono ich plikow dla annotacji."
            messagebox.showinfo(
                "Import Dataset",
                message,
                parent=self.view,
            )
            return

        try:
            self._run_dataset_import_with_progress(
                lambda progress_callback: self.service.create_task(
                    project_id=project_id,
                    task_name=task_name,
                    dataset_folder=dataset_folder,
                    image_paths=[],
                    video_path="",
                    frame_stride=30,
                    import_mode="dataset",
                    dataset_format=dataset_format,
                    allowed_label_types=allowed_label_types,
                    progress_callback=progress_callback,
                )
            )
        except ValueError as error:
            messagebox.showerror("Import Dataset", str(error), parent=self.view)
            return

        report = self.service.pop_last_dataset_import_report() or {}
        skipped = int(report.get("skipped_missing_images", 0))
        if skipped > 0:
            messagebox.showinfo(
                "Import Dataset",
                f"Pominieto {skipped} obrazow, bo nie znaleziono ich plikow dla annotacji.",
                parent=self.view,
            )

        if self.current_project_id == project_id:
            self.open_project(project_id)
            return
        self.show_projects_page()

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
        self._invalidate_task_workspace_cache()
        self.view.show_project_page(project, self.service.list_tasks(project_id))

    def open_create_task_dialog(self) -> None:
        if self.current_project_id is None:
            return

        initial_task_dialog_config = (
            dict(self.session_state.last_task_dialog_config)
            if isinstance(self.session_state.last_task_dialog_config, dict)
            else None
        )
        dialog = CreateTaskDialog(self.view, initial_config=initial_task_dialog_config)
        payload = dialog.show()
        if not payload:
            return

        dialog_state = payload.get("dialog_state")
        if isinstance(dialog_state, dict):
            self.session_state.last_task_dialog_config = dict(dialog_state)
            self._save_session_state()

        try:
            if payload["import_mode"] == "dataset":
                allowed_label_types = self._resolve_allowed_label_types(payload["dataset_folder"], payload.get("dataset_format", ""))
                if allowed_label_types == []:
                    return
                self._run_dataset_import_with_progress(
                    lambda progress_callback: self.service.create_task(
                        project_id=self.current_project_id,
                        task_name=payload["task_name"],
                        dataset_folder=payload["dataset_folder"],
                        dataset_folders=payload.get("dataset_folders", []),
                        image_paths=payload["image_paths"],
                        video_path=payload["video_path"],
                        video_paths=payload.get("video_paths", []),
                        frame_stride=payload["frame_stride"],
                        import_mode=payload["import_mode"],
                        dataset_format=payload.get("dataset_format", ""),
                        allowed_label_types=allowed_label_types,
                        progress_callback=progress_callback,
                    )
                )
            elif payload["import_mode"] == "video":
                self._run_video_import_with_progress(
                    lambda progress_callback: self.service.create_task(
                        project_id=self.current_project_id,
                        task_name=payload["task_name"],
                        dataset_folder=payload["dataset_folder"],
                        dataset_folders=payload.get("dataset_folders", []),
                        image_paths=payload["image_paths"],
                        video_path=payload["video_path"],
                        video_paths=payload.get("video_paths", []),
                        frame_stride=payload["frame_stride"],
                        import_mode=payload["import_mode"],
                        dataset_format=payload.get("dataset_format", ""),
                        progress_callback=progress_callback,
                    )
                )
            else:
                self.service.create_task(
                    project_id=self.current_project_id,
                    task_name=payload["task_name"],
                    dataset_folder=payload["dataset_folder"],
                    dataset_folders=payload.get("dataset_folders", []),
                    image_paths=payload["image_paths"],
                    video_path=payload["video_path"],
                    video_paths=payload.get("video_paths", []),
                    frame_stride=payload["frame_stride"],
                    import_mode=payload["import_mode"],
                    dataset_format=payload.get("dataset_format", ""),
                )
        except ValueError as error:
            messagebox.showerror("Task", str(error), parent=self.view)
            return

        if payload.get("import_mode") == "dataset":
            report = self.service.pop_last_dataset_import_report() or {}
            skipped = int(report.get("skipped_missing_images", 0))
            if skipped > 0:
                messagebox.showinfo(
                    "Task",
                    f"Pominieto {skipped} obrazow, bo nie znaleziono ich plikow dla annotacji.",
                    parent=self.view,
                )

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

        dialog = MergeProjectsDialog(self.view, options=[(item.id, item.name) for item in projects])
        payload = dialog.show()
        if not payload:
            return

        source_ids = [int(source_id) for source_id in payload.get("source_ids", [])]
        target_id = int(payload["target_id"])
        delete_sources = bool(payload.get("delete_sources", False))
        progress_dialog = BatchProgressDialog(self.view, "Scalanie projektow", max(1, len(source_ids)))
        progress_dialog.status_var.set("Rozpoczynanie scalania projektow...")
        progress_dialog.counter_var.set(f"0 / {len(source_ids)}")
        progress_dialog.details_var.set(f"Scalone projekty: 0 / {len(source_ids)}")
        progress_dialog.progress.configure(maximum=max(1, len(source_ids)), value=0)
        progress_dialog.set_indeterminate(True)
        progress_dialog._refresh()

        event_queue: Queue = Queue()
        merge_state: dict[str, object] = {"done": False, "error": None, "merged_count": 0}

        def merge_worker() -> None:
            merged_local = 0
            try:
                for index, source_id in enumerate(source_ids, start=1):
                    project_name = next((item.name for item in projects if item.id == source_id), f"ID {source_id}")
                    event_queue.put(("progress", index - 1, len(source_ids), project_name, merged_local))
                    self.service.merge_projects(source_id, target_id)
                    merged_local += 1
                    event_queue.put(("progress", index, len(source_ids), project_name, merged_local))
                event_queue.put(("done", merged_local))
            except Exception as error:
                event_queue.put(("error", error, merged_local))

        def poll_merge_queue() -> None:
            while True:
                try:
                    event = event_queue.get_nowait()
                except Empty:
                    break

                event_type = event[0]
                if event_type == "progress":
                    _, completed, total, project_name, merged_local = event
                    safe_total = max(1, int(total))
                    progress_dialog.set_indeterminate(False)
                    progress_dialog.progress.configure(maximum=safe_total, value=max(0, min(int(completed), safe_total)))
                    progress_dialog.counter_var.set(f"{int(completed)} / {int(total)}")
                    progress_dialog.status_var.set(f"Scalanie projektu {min(int(completed) + 1, int(total))}/{int(total)}: {project_name}")
                    progress_dialog.details_var.set(f"Scalone projekty: {int(merged_local)} / {int(total)}")
                    progress_dialog._refresh()
                    merge_state["merged_count"] = int(merged_local)
                elif event_type == "done":
                    merge_state["done"] = True
                    merge_state["merged_count"] = int(event[1])
                elif event_type == "error":
                    merge_state["done"] = True
                    merge_state["error"] = event[1]
                    merge_state["merged_count"] = int(event[2])

            if bool(merge_state["done"]):
                progress_dialog.set_indeterminate(False)
                progress_dialog.status_var.set("Scalanie zakonczone.")
                progress_dialog.details_var.set(
                    f"Scalone projekty: {int(merge_state['merged_count'])} / {len(source_ids)}"
                )
                progress_dialog._refresh()
                if progress_dialog.winfo_exists():
                    progress_dialog.close()
                return

            if progress_dialog.winfo_exists():
                self.view.after(50, poll_merge_queue)

        threading.Thread(target=merge_worker, daemon=True).start()
        self.view.after(0, poll_merge_queue)
        progress_dialog.wait_window(progress_dialog)

        if merge_state["error"] is not None:
            messagebox.showerror("Scalanie projektow", str(merge_state["error"]), parent=self.view)
            return
        merged_count = int(merge_state["merged_count"])

        deleted_count = 0
        if delete_sources:
            for source_id in source_ids:
                try:
                    self.service.delete_project(source_id)
                    deleted_count += 1
                except ValueError:
                    continue

        summary = f"Scalono {merged_count} projektow do wybranego projektu."
        if delete_sources:
            summary += f"\nUsunieto projekty zrodlowe: {deleted_count}."
        messagebox.showinfo("Scalanie projektow", summary, parent=self.view)
        self.show_projects_page()

    def delete_project(self) -> None:
        project_id = self.current_project_id
        if project_id is None:
            project_id = self.view.get_selected_project_id()
        if project_id is None:
            messagebox.showinfo("Usuwanie projektu", "Najpierw wybierz projekt.", parent=self.view)
            return

        try:
            project = self.service.get_project(project_id)
        except ValueError as error:
            messagebox.showerror("Usuwanie projektu", str(error), parent=self.view)
            self.show_projects_page()
            return

        if not messagebox.askyesno(
            "Usuwanie projektu",
            f"Czy na pewno usunac projekt '{project.name}' wraz z jego taskami?",
            parent=self.view,
        ):
            return

        self.service.delete_project(project_id)
        self.current_project_id = None
        self.current_task_id = None
        self.current_image_index = 0
        self._invalidate_task_workspace_cache()
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

    def delete_task(self) -> None:
        if self.current_project_id is None:
            messagebox.showinfo("Usuwanie taska", "Najpierw otworz projekt.", parent=self.view)
            return

        task_id = self.current_task_id or self.view.get_selected_task_id()
        if task_id is None:
            messagebox.showinfo("Usuwanie taska", "Najpierw wybierz task.", parent=self.view)
            return

        task = next((item for item in self.service.list_tasks(self.current_project_id) if item.id == task_id), None)
        if task is None:
            messagebox.showerror("Usuwanie taska", "Nie znaleziono wybranego taska.", parent=self.view)
            self.open_project(self.current_project_id)
            return

        if not messagebox.askyesno(
            "Usuwanie taska",
            f"Czy na pewno usunac task '{task.name}'?",
            parent=self.view,
        ):
            return

        self.service.delete_task(task_id)
        self.current_task_id = None
        self.current_image_index = 0
        self._invalidate_task_workspace_cache()
        self.open_project(self.current_project_id)

    def open_task(self, task_id: int) -> None:
        try:
            workspace = self._get_task_workspace(task_id, force_reload=self.current_task_id != task_id)
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

    def change_image(
        self,
        step: int,
        combo_value: str = "",
        annotation_definition: dict[str, object] | None = None,
    ) -> None:
        if self.current_task_id is None:
            return

        workspace = self._get_task_workspace(self.current_task_id)
        images = workspace["images"]
        if images and combo_value and annotation_definition is not None:
            image_id = images[self.current_image_index].id
            label_id = int(combo_value.split("|", maxsplit=1)[0])
            try:
                self.service.add_annotation(image_id, label_id, "", annotation_definition)
            except ValueError as error:
                messagebox.showerror("Adnotacje", str(error), parent=self.view)
                return
            workspace = self._get_task_workspace(self.current_task_id, force_reload=True)
            images = workspace["images"]

        if not images:
            self.current_image_index = 0
        else:
            self.current_image_index = (self.current_image_index + step) % len(images)
        self.view.show_task_page(workspace, self.current_image_index)

    def add_annotation(
        self,
        label_template_id: int,
        note: str,
        annotation_definition: dict[str, object] | None = None,
    ) -> None:
        if self.current_task_id is None:
            return

        workspace = self._get_task_workspace(self.current_task_id)
        images = workspace["images"]
        if not images:
            messagebox.showinfo("Adnotacje", "Ten task nie ma obrazow.", parent=self.view)
            return

        image_id = images[self.current_image_index].id
        try:
            self.service.add_annotation(image_id, label_template_id, note, annotation_definition)
        except ValueError as error:
            messagebox.showerror("Adnotacje", str(error), parent=self.view)
            return

        workspace = self._get_task_workspace(self.current_task_id, force_reload=True)
        self.view.refresh_task_page(workspace, self.current_image_index)

    def copy_annotation_from_previous_image(self, combo_value: str) -> None:
        if self.current_task_id is None:
            return
        if not combo_value:
            messagebox.showinfo("Adnotacje", "Najpierw wybierz etykiete do skopiowania.", parent=self.view)
            return

        workspace = self._get_task_workspace(self.current_task_id)
        images = workspace["images"]
        if not images:
            messagebox.showinfo("Adnotacje", "Ten task nie ma obrazow.", parent=self.view)
            return
        if self.current_image_index <= 0:
            messagebox.showinfo("Adnotacje", "To jest pierwsze zdjecie, nie ma skad skopiowac etykiety.", parent=self.view)
            return

        label_id = int(combo_value.split("|", maxsplit=1)[0])
        current_image = images[self.current_image_index]
        previous_image = images[self.current_image_index - 1]
        previous_annotations = workspace["annotations"].get(previous_image.id, [])
        source_annotation = next(
            (annotation for annotation in previous_annotations if annotation.label_template_id == label_id),
            None,
        )
        if source_annotation is None:
            messagebox.showinfo(
                "Adnotacje",
                "Na poprzednim zdjeciu nie ma annotacji dla wybranej etykiety.",
                parent=self.view,
            )
            return

        try:
            self.service.add_annotation(
                current_image.id,
                label_id,
                source_annotation.note or "",
                source_annotation.annotation_definition,
            )
        except ValueError as error:
            messagebox.showerror("Adnotacje", str(error), parent=self.view)
            return

        workspace = self._get_task_workspace(self.current_task_id, force_reload=True)
        self.view.refresh_task_page(workspace, self.current_image_index)

    def toggle_annotation_visibility(self, annotation_id: int) -> None:
        if self.current_task_id is None:
            return
        self.service.toggle_annotation_visibility(annotation_id)
        workspace = self._get_task_workspace(self.current_task_id, force_reload=True)
        self.view.refresh_task_page(workspace, self.current_image_index)

    def update_annotation(self, annotation_id: int, annotation_definition: dict[str, object]) -> None:
        try:
            self.service.update_annotation(annotation_id, annotation_definition)
        except ValueError as error:
            messagebox.showerror("Adnotacje", str(error), parent=self.view)
            return
        if self.current_task_id is None:
            return
        workspace = self._get_task_workspace(self.current_task_id, force_reload=True)
        self.view.refresh_task_page(workspace, self.current_image_index)

    def delete_annotation(self, annotation_id: int) -> None:
        if self.current_task_id is None:
            return
        self.service.delete_annotation(annotation_id)
        workspace = self._get_task_workspace(self.current_task_id, force_reload=True)
        self.view.refresh_task_page(workspace, self.current_image_index)

    def delete_current_image(self) -> None:
        if self.current_task_id is None:
            return

        workspace = self._get_task_workspace(self.current_task_id)
        images = workspace["images"]
        if not images:
            return

        image_id = images[self.current_image_index].id
        self.service.delete_image(image_id)
        self.current_image_index = max(0, self.current_image_index - 1)
        workspace = self._get_task_workspace(self.current_task_id, force_reload=True)
        self.view.refresh_task_page(workspace, self.current_image_index)

    def auto_label_current_image(self) -> None:
        context = self._get_auto_label_context()
        if context is None:
            return

        workspace, images, available_modes = context

        dialog = ModelInferenceDialog(self.view, available_modes, initial_config=self._get_last_model_config_for_modes(available_modes))
        payload = dialog.show()
        if not payload:
            return
        self._run_auto_label_payload(workspace, images, payload)

    def auto_label_task_images(self) -> None:
        context = self._get_auto_label_context()
        if context is None:
            return

        workspace, images, available_modes = context
        dialog = ModelInferenceDialog(self.view, available_modes, initial_config=self._get_last_model_config_for_modes(available_modes))
        payload = dialog.show()
        if not payload:
            return
        if not messagebox.askyesno(
            "Model",
            f"Uruchomic autoadnotacje dla wszystkich {len(images)} obrazow w tym tasku?",
            parent=self.view,
        ):
            return
        self._run_auto_label_payload(workspace, images, payload, target_image_indexes=list(range(len(images))))

    def run_last_model_for_current_image(self) -> None:
        context = self._get_auto_label_context()
        if context is None:
            return

        workspace, images, available_modes = context
        saved_config = self.session_state.last_model_config
        if not isinstance(saved_config, dict):
            messagebox.showinfo(
                "Model",
                "Brak zapisanej konfiguracji ostatniego modelu. Najpierw uruchom autoadnotacje i zatwierdz ustawienia modelu.",
                parent=self.view,
            )
            return

        saved_mode = str(saved_config.get("mode") or "").strip()
        if saved_mode not in available_modes:
            messagebox.showinfo(
                "Model",
                "Ostatnio zapisany model nie pasuje do aktualnego projektu lub etykiet. Otworz zwykle okno autoadnotacji i wybierz konfiguracje ponownie.",
                parent=self.view,
            )
            return

        self._run_auto_label_payload(workspace, images, dict(saved_config), save_as_last_used=False)

    def on_close(self) -> None:
        self._save_session_state()
        self.view.destroy()