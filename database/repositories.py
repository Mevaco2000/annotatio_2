from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from database.sqlite_db import DatabaseManager
from model.entities import (
    AnnotationRecord,
    ImageRecord,
    LabelTemplate,
    ProjectDetails,
    ProjectSummary,
    SessionState,
    TaskSummary,
)


class AppRepository:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def list_projects(self) -> list[ProjectSummary]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    p.id,
                    p.name,
                    p.project_type,
                    p.storage_path,
                    p.updated_at,
                    (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id) AS task_count,
                    (
                        SELECT COUNT(*)
                        FROM images i
                        JOIN tasks t ON t.id = i.task_id
                        WHERE t.project_id = p.id AND i.is_deleted = 0
                    ) AS image_count,
                    (
                        SELECT COUNT(*)
                        FROM annotations a
                        JOIN images i ON i.id = a.image_id
                        JOIN tasks t ON t.id = i.task_id
                        WHERE t.project_id = p.id AND i.is_deleted = 0
                    ) AS annotation_count,
                    (
                        SELECT i.file_path
                        FROM images i
                        JOIN tasks t ON t.id = i.task_id
                        WHERE t.project_id = p.id AND i.is_deleted = 0
                        ORDER BY t.id, i.sort_index
                        LIMIT 1
                    ) AS preview_image_path
                FROM projects p
                ORDER BY p.updated_at DESC, p.name COLLATE NOCASE
                """
            ).fetchall()

        return [
            ProjectSummary(
                id=row["id"],
                name=row["name"],
                project_type=row["project_type"],
                task_count=row["task_count"],
                image_count=row["image_count"],
                annotation_count=row["annotation_count"],
                updated_at=row["updated_at"],
                preview_image_path=row["preview_image_path"],
                storage_path=row["storage_path"],
            )
            for row in rows
        ]

    def create_project(
        self,
        name: str,
        project_type: str,
        labels: list[LabelTemplate],
        storage_path: str | None,
    ) -> int:
        timestamp = self._now()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO projects(name, project_type, storage_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, project_type, storage_path, timestamp, timestamp),
            )
            project_id = int(cursor.lastrowid)

            for label in labels:
                connection.execute(
                    """
                    INSERT INTO label_templates(project_id, name, label_type, preview_image_path, preview_definition_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        label.name,
                        label.label_type,
                        label.preview_image_path,
                        json.dumps(label.preview_definition, ensure_ascii=False) if label.preview_definition is not None else None,
                        timestamp,
                    ),
                )
        return project_id

    def get_project(self, project_id: int) -> ProjectDetails | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, project_type, storage_path, created_at, updated_at
                FROM projects
                WHERE id = ?
                """,
                (project_id,),
            ).fetchone()
            if row is None:
                return None

        return ProjectDetails(
            id=row["id"],
            name=row["name"],
            project_type=row["project_type"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            storage_path=row["storage_path"],
        )

    def list_label_templates(self, project_id: int) -> list[LabelTemplate]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, label_type, preview_image_path, preview_definition_json
                FROM label_templates
                WHERE project_id = ?
                ORDER BY name COLLATE NOCASE
                """,
                (project_id,),
            ).fetchall()

        return [
            LabelTemplate(
                id=row["id"],
                name=row["name"],
                label_type=row["label_type"],
                preview_image_path=row["preview_image_path"],
                preview_definition=json.loads(row["preview_definition_json"]) if row["preview_definition_json"] else None,
            )
            for row in rows
        ]

    def create_task(self, project_id: int, task_name: str, dataset_path: str, image_paths: list[str]) -> int:
        timestamp = self._now()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tasks(project_id, name, dataset_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project_id, task_name, dataset_path, timestamp, timestamp),
            )
            task_id = int(cursor.lastrowid)

            for index, image_path in enumerate(image_paths):
                connection.execute(
                    """
                    INSERT INTO images(task_id, file_path, sort_index, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (task_id, image_path, index, timestamp),
                )

            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, project_id),
            )
        return task_id

    def list_tasks(self, project_id: int) -> list[TaskSummary]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    t.id,
                    t.project_id,
                    t.name,
                    t.dataset_path,
                    t.updated_at,
                    (
                        SELECT COUNT(*)
                        FROM images i
                        WHERE i.task_id = t.id AND i.is_deleted = 0
                    ) AS image_count,
                    (
                        SELECT COUNT(*)
                        FROM annotations a
                        JOIN images i ON i.id = a.image_id
                        WHERE i.task_id = t.id AND i.is_deleted = 0
                    ) AS annotation_count,
                    (
                        SELECT i.file_path
                        FROM images i
                        WHERE i.task_id = t.id AND i.is_deleted = 0
                        ORDER BY i.sort_index
                        LIMIT 1
                    ) AS preview_image_path
                FROM tasks t
                WHERE t.project_id = ?
                ORDER BY t.updated_at DESC, t.name COLLATE NOCASE
                """,
                (project_id,),
            ).fetchall()

        return [
            TaskSummary(
                id=row["id"],
                project_id=row["project_id"],
                name=row["name"],
                dataset_path=row["dataset_path"],
                image_count=row["image_count"],
                annotation_count=row["annotation_count"],
                updated_at=row["updated_at"],
                preview_image_path=row["preview_image_path"],
            )
            for row in rows
        ]

    def list_images(self, task_id: int) -> list[ImageRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, task_id, file_path, sort_index, is_deleted
                FROM images
                WHERE task_id = ? AND is_deleted = 0
                ORDER BY sort_index
                """,
                (task_id,),
            ).fetchall()

        return [
            ImageRecord(
                id=row["id"],
                task_id=row["task_id"],
                file_path=row["file_path"],
                sort_index=row["sort_index"],
                is_deleted=bool(row["is_deleted"]),
            )
            for row in rows
        ]

    def list_annotations(self, image_id: int) -> list[AnnotationRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, image_id, label_template_id, label_name, label_type, annotation_definition_json, is_visible, source, note
                FROM annotations
                WHERE image_id = ?
                ORDER BY id DESC
                """,
                (image_id,),
            ).fetchall()

        return [
            AnnotationRecord(
                id=row["id"],
                image_id=row["image_id"],
                label_template_id=row["label_template_id"],
                label_name=row["label_name"],
                label_type=row["label_type"],
                annotation_definition=json.loads(row["annotation_definition_json"]) if row["annotation_definition_json"] else None,
                is_visible=bool(row["is_visible"]),
                source=row["source"],
                note=row["note"],
            )
            for row in rows
        ]

    def list_annotations_for_task(self, task_id: int) -> dict[int, list[AnnotationRecord]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT a.id, a.image_id, a.label_template_id, a.label_name, a.label_type, a.annotation_definition_json, a.is_visible, a.source, a.note
                FROM annotations a
                JOIN images i ON i.id = a.image_id
                WHERE i.task_id = ? AND i.is_deleted = 0
                ORDER BY a.image_id, a.id DESC
                """,
                (task_id,),
            ).fetchall()

        annotations_by_image: dict[int, list[AnnotationRecord]] = {}
        for row in rows:
            annotations_by_image.setdefault(row["image_id"], []).append(
                AnnotationRecord(
                    id=row["id"],
                    image_id=row["image_id"],
                    label_template_id=row["label_template_id"],
                    label_name=row["label_name"],
                    label_type=row["label_type"],
                    annotation_definition=json.loads(row["annotation_definition_json"]) if row["annotation_definition_json"] else None,
                    is_visible=bool(row["is_visible"]),
                    source=row["source"],
                    note=row["note"],
                )
            )
        return annotations_by_image

    def add_annotation(
        self,
        image_id: int,
        label_template_id: int,
        label_name: str,
        label_type: str,
        annotation_definition: dict[str, object] | None,
        source: str,
        note: str,
    ) -> None:
        timestamp = self._now()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO annotations(image_id, label_template_id, label_name, label_type, annotation_definition_json, is_visible, source, note, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    image_id,
                    label_template_id,
                    label_name,
                    label_type,
                    json.dumps(annotation_definition, ensure_ascii=False) if annotation_definition is not None else None,
                    source,
                    note,
                    timestamp,
                ),
            )
            self._touch_from_image(connection, image_id)

    def get_annotation(self, annotation_id: int) -> AnnotationRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, image_id, label_template_id, label_name, label_type, annotation_definition_json, is_visible, source, note
                FROM annotations
                WHERE id = ?
                """,
                (annotation_id,),
            ).fetchone()

        if row is None:
            return None

        return AnnotationRecord(
            id=row["id"],
            image_id=row["image_id"],
            label_template_id=row["label_template_id"],
            label_name=row["label_name"],
            label_type=row["label_type"],
            annotation_definition=json.loads(row["annotation_definition_json"]) if row["annotation_definition_json"] else None,
            is_visible=bool(row["is_visible"]),
            source=row["source"],
            note=row["note"],
        )

    def update_annotation_definition(self, annotation_id: int, annotation_definition: dict[str, object] | None) -> None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT image_id FROM annotations WHERE id = ?",
                (annotation_id,),
            ).fetchone()
            if row is None:
                return
            connection.execute(
                "UPDATE annotations SET annotation_definition_json = ? WHERE id = ?",
                (json.dumps(annotation_definition, ensure_ascii=False) if annotation_definition is not None else None, annotation_id),
            )
            self._touch_from_image(connection, row["image_id"])

    def toggle_annotation_visibility(self, annotation_id: int) -> None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT image_id, is_visible FROM annotations WHERE id = ?",
                (annotation_id,),
            ).fetchone()
            if row is None:
                return
            connection.execute(
                "UPDATE annotations SET is_visible = ? WHERE id = ?",
                (0 if row["is_visible"] else 1, annotation_id),
            )
            self._touch_from_image(connection, row["image_id"])

    def delete_annotation(self, annotation_id: int) -> None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT image_id FROM annotations WHERE id = ?",
                (annotation_id,),
            ).fetchone()
            if row is None:
                return
            connection.execute("DELETE FROM annotations WHERE id = ?", (annotation_id,))
            self._touch_from_image(connection, row["image_id"])

    def delete_image(self, image_id: int) -> None:
        timestamp = self._now()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT task_id FROM images WHERE id = ?",
                (image_id,),
            ).fetchone()
            if row is None:
                return
            connection.execute(
                "UPDATE images SET is_deleted = 1 WHERE id = ?",
                (image_id,),
            )
            self._touch_task(connection, row["task_id"], timestamp)

    def delete_project(self, project_id: int) -> None:
        with self.database.connect() as connection:
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def delete_task(self, task_id: int) -> None:
        timestamp = self._now()
        with self.database.connect() as connection:
            row = connection.execute("SELECT project_id FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                return
            connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, row["project_id"]),
            )

    def merge_projects(self, source_project_id: int, target_project_id: int) -> None:
        if source_project_id == target_project_id:
            raise ValueError("Projekt zrodlowy i docelowy musza byc rozne.")

        timestamp = self._now()
        with self.database.connect() as connection:
            label_rows = connection.execute(
                "SELECT name, label_type, preview_image_path, preview_definition_json FROM label_templates WHERE project_id = ?",
                (source_project_id,),
            ).fetchall()
            existing_labels = {
                (row["name"], row["label_type"])
                for row in connection.execute(
                    "SELECT name, label_type FROM label_templates WHERE project_id = ?",
                    (target_project_id,),
                ).fetchall()
            }
            for row in label_rows:
                key = (row["name"], row["label_type"])
                if key in existing_labels:
                    continue
                connection.execute(
                    """
                    INSERT INTO label_templates(project_id, name, label_type, preview_image_path, preview_definition_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        target_project_id,
                        row["name"],
                        row["label_type"],
                        row["preview_image_path"],
                        row["preview_definition_json"],
                        timestamp,
                    ),
                )

            task_rows = connection.execute(
                "SELECT id, name, dataset_path FROM tasks WHERE project_id = ? ORDER BY id",
                (source_project_id,),
            ).fetchall()
            for task_row in task_rows:
                new_task_id = int(
                    connection.execute(
                        """
                        INSERT INTO tasks(project_id, name, dataset_path, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            target_project_id,
                            f"{task_row['name']} (merged)",
                            task_row["dataset_path"],
                            timestamp,
                            timestamp,
                        ),
                    ).lastrowid
                )
                self._copy_task_payload(connection, task_row["id"], new_task_id, timestamp)

            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, target_project_id),
            )

    def merge_tasks(self, source_task_id: int, target_task_id: int) -> None:
        if source_task_id == target_task_id:
            raise ValueError("Task zrodlowy i docelowy musza byc rozne.")

        timestamp = self._now()
        with self.database.connect() as connection:
            self._copy_task_payload(connection, source_task_id, target_task_id, timestamp)
            self._touch_task(connection, target_task_id, timestamp)

    def _copy_task_payload(self, connection, source_task_id: int, target_task_id: int, timestamp: str) -> None:
        image_rows = connection.execute(
            "SELECT id, file_path FROM images WHERE task_id = ? AND is_deleted = 0 ORDER BY sort_index",
            (source_task_id,),
        ).fetchall()
        next_index = connection.execute(
            "SELECT COALESCE(MAX(sort_index), -1) + 1 AS next_index FROM images WHERE task_id = ?",
            (target_task_id,),
        ).fetchone()["next_index"]

        for offset, image_row in enumerate(image_rows):
            new_image_id = int(
                connection.execute(
                    """
                    INSERT INTO images(task_id, file_path, sort_index, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (target_task_id, image_row["file_path"], next_index + offset, timestamp),
                ).lastrowid
            )
            annotation_rows = connection.execute(
                """
                SELECT label_template_id, label_name, label_type, annotation_definition_json, is_visible, source, note, created_at
                FROM annotations
                WHERE image_id = ?
                ORDER BY id
                """,
                (image_row["id"],),
            ).fetchall()
            for annotation_row in annotation_rows:
                connection.execute(
                    """
                    INSERT INTO annotations(image_id, label_template_id, label_name, label_type, annotation_definition_json, is_visible, source, note, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_image_id,
                        annotation_row["label_template_id"],
                        annotation_row["label_name"],
                        annotation_row["label_type"],
                        annotation_row["annotation_definition_json"],
                        annotation_row["is_visible"],
                        annotation_row["source"],
                        annotation_row["note"],
                        annotation_row["created_at"],
                    ),
                )

    def save_session_state(self, session: SessionState) -> None:
        timestamp = self._now()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO app_sessions(
                    id,
                    last_page,
                    last_project_id,
                    last_task_id,
                    window_width,
                    window_height,
                    last_model_config_json,
                    last_task_dialog_config_json,
                    updated_at
                )
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_page = excluded.last_page,
                    last_project_id = excluded.last_project_id,
                    last_task_id = excluded.last_task_id,
                    window_width = excluded.window_width,
                    window_height = excluded.window_height,
                    last_model_config_json = excluded.last_model_config_json,
                    last_task_dialog_config_json = excluded.last_task_dialog_config_json,
                    updated_at = excluded.updated_at
                """,
                (
                    session.last_page,
                    session.last_project_id,
                    session.last_task_id,
                    session.window_width,
                    session.window_height,
                    json.dumps(session.last_model_config, ensure_ascii=False) if session.last_model_config is not None else None,
                    json.dumps(session.last_task_dialog_config, ensure_ascii=False)
                    if session.last_task_dialog_config is not None
                    else None,
                    timestamp,
                ),
            )

    def load_session_state(self) -> SessionState:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT last_page, last_project_id, last_task_id, window_width, window_height, last_model_config_json, last_task_dialog_config_json FROM app_sessions WHERE id = 1"
            ).fetchone()

        if row is None:
            return SessionState()

        return SessionState(
            last_page=row["last_page"],
            last_project_id=row["last_project_id"],
            last_task_id=row["last_task_id"],
            window_width=row["window_width"],
            window_height=row["window_height"],
            last_model_config=json.loads(row["last_model_config_json"]) if row["last_model_config_json"] else None,
            last_task_dialog_config=
            json.loads(row["last_task_dialog_config_json"]) if row["last_task_dialog_config_json"] else None,
        )

    def _touch_from_image(self, connection, image_id: int) -> None:
        row = connection.execute(
            """
            SELECT t.id AS task_id, p.id AS project_id
            FROM images i
            JOIN tasks t ON t.id = i.task_id
            JOIN projects p ON p.id = t.project_id
            WHERE i.id = ?
            """,
            (image_id,),
        ).fetchone()
        if row is None:
            return
        self._touch_task(connection, row["task_id"], self._now())

    def _touch_task(self, connection, task_id: int, timestamp: str) -> None:
        connection.execute(
            "UPDATE tasks SET updated_at = ? WHERE id = ?",
            (timestamp, task_id),
        )
        project_row = connection.execute(
            "SELECT project_id FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if project_row is not None:
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, project_row["project_id"]),
            )