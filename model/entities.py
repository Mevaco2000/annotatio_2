from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LabelTemplate:
    id: int | None
    name: str
    label_type: str
    preview_image_path: str | None = None
    preview_definition: dict[str, object] | None = None


@dataclass(slots=True)
class ProjectSummary:
    id: int
    name: str
    project_type: str
    task_count: int
    image_count: int
    annotation_count: int
    updated_at: str
    preview_image_path: str | None
    storage_path: str | None


@dataclass(slots=True)
class ProjectDetails:
    id: int
    name: str
    project_type: str
    created_at: str
    updated_at: str
    storage_path: str | None


@dataclass(slots=True)
class TaskSummary:
    id: int
    project_id: int
    name: str
    dataset_path: str | None
    image_count: int
    annotation_count: int
    updated_at: str
    preview_image_path: str | None


@dataclass(slots=True)
class ImageRecord:
    id: int
    task_id: int
    file_path: str
    sort_index: int
    is_deleted: bool


@dataclass(slots=True)
class AnnotationRecord:
    id: int
    image_id: int
    label_template_id: int | None
    label_name: str
    label_type: str
    annotation_definition: dict[str, object] | None
    is_visible: bool
    source: str
    note: str | None


@dataclass(slots=True)
class SessionState:
    last_page: str = "home"
    last_project_id: int | None = None
    last_task_id: int | None = None
    window_width: int = 1400
    window_height: int = 900
    last_model_config: dict[str, object] | None = None