from __future__ import annotations

import sqlite3
from pathlib import Path


class DatabaseManager:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    project_type TEXT NOT NULL,
                    storage_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS label_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    label_type TEXT NOT NULL,
                    preview_image_path TEXT,
                    preview_definition_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    dataset_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    sort_index INTEGER NOT NULL,
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS annotations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER NOT NULL,
                    label_template_id INTEGER,
                    label_name TEXT NOT NULL,
                    label_type TEXT NOT NULL,
                    annotation_definition_json TEXT,
                    is_visible INTEGER NOT NULL DEFAULT 1,
                    source TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE,
                    FOREIGN KEY(label_template_id) REFERENCES label_templates(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS app_sessions (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    last_page TEXT NOT NULL,
                    last_project_id INTEGER,
                    last_task_id INTEGER,
                    window_width INTEGER NOT NULL,
                    window_height INTEGER NOT NULL,
                    last_model_config_json TEXT,
                    last_task_dialog_config_json TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(connection, "projects", "storage_path", "TEXT")
            self._ensure_column(connection, "label_templates", "preview_definition_json", "TEXT")
            self._ensure_column(connection, "annotations", "annotation_definition_json", "TEXT")
            self._ensure_column(connection, "app_sessions", "last_model_config_json", "TEXT")
            self._ensure_column(connection, "app_sessions", "last_task_dialog_config_json", "TEXT")

    def _ensure_column(self, connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}
        if column_name not in columns:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")