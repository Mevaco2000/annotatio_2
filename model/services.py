from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path

from database.repositories import AppRepository
from model.entities import LabelTemplate, SessionState


class AppService:
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}

    def __init__(self, repository: AppRepository) -> None:
        self.repository = repository

    def get_start_description(self) -> str:
        return (
            "Ta aplikacja jest prostym szkieletem desktopowym do zarzadzania projektami annotacji.\n\n"
            "Jak pracowac:\n"
            "1. Wejdz do zakladki Projects i utworz projekt.\n"
            "2. Dodaj etykiety projektu przez okno dialogowe.\n"
            "3. Otworz projekt i stworz task na podstawie folderu z obrazami.\n"
            "4. Otworz task, przechodz po zdjeciach i przypisuj etykiety.\n"
            "5. Eksportuj wynik do JSON, CSV albo TXT.\n\n"
            "Dane projektow, adnotacji i ostatniej sesji sa zapisywane w SQLite."
        )

    def get_settings_description(self) -> str:
        return (
            "Sekcja Settings jest przygotowana jako proste miejsce na przyszle ustawienia aplikacji.\n\n"
            "Aktualnie stan okna i ostatnio otwarta strona sa zapisywane automatycznie w SQLite."
        )

    def get_info_description(self) -> str:
        return (
            "Annotatio zostalo rozbite na warstwy zgodnie z prostym wzorcem: GUI, model, controller i database.\n\n"
            "GUI odpowiada za widoki Tkinter, model za logike, controller za przeplyw zdarzen, a database za SQLite i repozytorium."
        )

    def list_projects(self):
        return self.repository.list_projects()

    def create_project(self, name: str, project_type: str, labels: list[LabelTemplate]) -> int:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Nazwa projektu nie moze byc pusta.")
        if not labels:
            raise ValueError("Projekt musi miec przynajmniej jedna etykiete.")
        return self.repository.create_project(clean_name, project_type, labels)

    def get_project(self, project_id: int):
        project = self.repository.get_project(project_id)
        if project is None:
            raise ValueError("Nie znaleziono projektu.")
        return project

    def list_tasks(self, project_id: int):
        return self.repository.list_tasks(project_id)

    def create_task(self, project_id: int, task_name: str, dataset_folder: str) -> int:
        clean_name = task_name.strip()
        if not clean_name:
            raise ValueError("Nazwa taska nie moze byc pusta.")

        image_paths: list[str] = []
        clean_folder = dataset_folder.strip()
        if clean_folder:
            folder = Path(clean_folder)
            if not folder.exists() or not folder.is_dir():
                raise ValueError("Wskazany folder z datasetem nie istnieje.")
            image_paths = [
                str(path)
                for path in sorted(folder.iterdir())
                if path.is_file() and path.suffix.lower() in self.IMAGE_EXTENSIONS
            ]
            if not image_paths:
                raise ValueError("W wybranym folderze nie ma obslugiwanych obrazow.")

        return self.repository.create_task(project_id, clean_name, clean_folder or None, image_paths)

    def get_task_workspace(self, task_id: int) -> dict:
        task = None
        for project in self.list_projects():
            tasks = self.repository.list_tasks(project.id)
            task = next((item for item in tasks if item.id == task_id), None)
            if task:
                project_details = self.get_project(project.id)
                break
        else:
            raise ValueError("Nie znaleziono taska.")

        labels = self.repository.list_label_templates(task.project_id)
        images = self.repository.list_images(task_id)
        annotations = {image.id: self.repository.list_annotations(image.id) for image in images}
        return {
            "project": project_details,
            "task": task,
            "labels": labels,
            "images": images,
            "annotations": annotations,
        }

    def add_annotation(self, image_id: int, label_template_id: int, note: str) -> None:
        label = self._find_label_template(label_template_id)
        self.repository.add_annotation(
            image_id=image_id,
            label_template_id=label_template_id,
            label_name=label.name,
            label_type=label.label_type,
            source="manual",
            note=note,
        )

    def toggle_annotation_visibility(self, annotation_id: int) -> None:
        self.repository.toggle_annotation_visibility(annotation_id)

    def delete_annotation(self, annotation_id: int) -> None:
        self.repository.delete_annotation(annotation_id)

    def delete_image(self, image_id: int) -> None:
        self.repository.delete_image(image_id)

    def auto_label_image(self, image_id: int) -> None:
        project_labels = []
        for project in self.list_projects():
            labels = self.repository.list_label_templates(project.id)
            if labels:
                project_labels = labels
                break
        if not project_labels:
            raise ValueError("Brak zdefiniowanych etykiet do modelowego oznaczania.")

        label = project_labels[0]
        self.repository.add_annotation(
            image_id=image_id,
            label_template_id=label.id or 0,
            label_name=label.name,
            label_type=label.label_type,
            source="model",
            note="Automatycznie zasugerowane",
        )

    def merge_projects(self, source_project_id: int, target_project_id: int) -> None:
        self.repository.merge_projects(source_project_id, target_project_id)

    def merge_tasks(self, source_task_id: int, target_task_id: int) -> None:
        self.repository.merge_tasks(source_task_id, target_task_id)

    def export_project(
        self,
        project_id: int,
        export_format: str,
        split: dict[str, int],
        include_images: bool,
        destination_folder: str,
    ) -> str:
        project = self.get_project(project_id)
        tasks = self.list_tasks(project_id)
        if not tasks:
            raise ValueError("Projekt nie ma taskow do eksportu.")

        image_rows: list[dict] = []
        for task in tasks:
            for image in self.repository.list_images(task.id):
                image_rows.append(
                    {
                        "task_name": task.name,
                        "image": image,
                        "annotations": self.repository.list_annotations(image.id),
                    }
                )

        if not image_rows:
            raise ValueError("Projekt nie ma obrazow do eksportu.")

        export_root = Path(destination_folder) / f"{project.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        export_root.mkdir(parents=True, exist_ok=True)

        split_names = self._build_split_assignments(image_rows, split)
        labels = self.repository.list_label_templates(project_id)
        manifest = {
            "project": {
                "id": project.id,
                "name": project.name,
                "project_type": project.project_type,
                "export_format": export_format,
            },
            "labels": [label.__dict__ for label in labels],
            "items": [],
        }

        for index, item in enumerate(image_rows):
            split_name = split_names[index]
            image = item["image"]
            destination_image = None
            if include_images:
                images_dir = export_root / split_name / "images"
                images_dir.mkdir(parents=True, exist_ok=True)
                source_path = Path(image.file_path)
                if source_path.exists():
                    destination_image = images_dir / source_path.name
                    shutil.copy2(source_path, destination_image)

            manifest["items"].append(
                {
                    "split": split_name,
                    "task": item["task_name"],
                    "image_name": Path(image.file_path).name,
                    "image_path": str(destination_image) if destination_image else image.file_path,
                    "annotations": [annotation.__dict__ for annotation in item["annotations"]],
                }
            )

        if export_format == "JSON (native)":
            self._export_json(export_root, manifest)
        elif export_format == "CSV":
            self._export_csv(export_root, manifest)
        else:
            self._export_txt(export_root, manifest)

        return str(export_root)

    def save_session_state(self, session: SessionState) -> None:
        self.repository.save_session_state(session)

    def load_session_state(self) -> SessionState:
        return self.repository.load_session_state()

    def _find_label_template(self, label_template_id: int) -> LabelTemplate:
        for project in self.list_projects():
            for label in self.repository.list_label_templates(project.id):
                if label.id == label_template_id:
                    return label
        raise ValueError("Nie znaleziono wybranej etykiety.")

    def _build_split_assignments(self, image_rows: list[dict], split: dict[str, int]) -> list[str]:
        total = len(image_rows)
        train_count = round(total * split["train"] / 100)
        valid_count = round(total * split["valid"] / 100)
        if train_count + valid_count > total:
            valid_count = max(0, total - train_count)
        test_count = max(0, total - train_count - valid_count)

        assignments = ["train"] * train_count + ["valid"] * valid_count + ["test"] * test_count
        while len(assignments) < total:
            assignments.append("test")
        return assignments[:total]

    def _export_json(self, export_root: Path, manifest: dict) -> None:
        with (export_root / "dataset.json").open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, ensure_ascii=False)

    def _export_csv(self, export_root: Path, manifest: dict) -> None:
        with (export_root / "annotations.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["split", "task", "image_name", "label_name", "label_type", "source", "visible", "note"])
            for item in manifest["items"]:
                if not item["annotations"]:
                    writer.writerow([item["split"], item["task"], item["image_name"], "", "", "", "", ""])
                    continue
                for annotation in item["annotations"]:
                    writer.writerow(
                        [
                            item["split"],
                            item["task"],
                            item["image_name"],
                            annotation["label_name"],
                            annotation["label_type"],
                            annotation["source"],
                            annotation["is_visible"],
                            annotation["note"],
                        ]
                    )

    def _export_txt(self, export_root: Path, manifest: dict) -> None:
        lines = []
        lines.append(f"Projekt: {manifest['project']['name']}")
        lines.append(f"Typ: {manifest['project']['project_type']}")
        lines.append("")
        for item in manifest["items"]:
            lines.append(f"[{item['split']}] {item['task']} -> {item['image_name']}")
            if item["annotations"]:
                for annotation in item["annotations"]:
                    lines.append(
                        f"  - {annotation['label_name']} ({annotation['label_type']}), source={annotation['source']}, visible={annotation['is_visible']}"
                    )
            else:
                lines.append("  - brak annotacji")
        (export_root / "dataset.txt").write_text("\n".join(lines), encoding="utf-8")

    def get_start_description(self) -> str:
        return (
            "Annotatio 2 to prosty desktopowy szkielet aplikacji do zarządzania projektami "
            "annotacyjnymi dla AI.\n\n"
            "Jak pracować:\n"
            "1. W pasku bocznym przejdź do Projects.\n"
            "2. Utwórz projekt i zdefiniuj etykiety.\n"
            "3. W projekcie dodawaj taski, gdzie każdy zaimportowany dataset jest osobnym taskiem.\n"
            "4. W tasku przeglądaj obrazy, dodawaj label do aktualnego zdjęcia, ukrywaj lub usuwaj istniejące oznaczenia.\n"
            "5. Eksport datasetu zapisuje też stan sesji aplikacji w SQLite, więc po ponownym uruchomieniu wracasz do ostatniego miejsca.\n\n"
            "Architektura jest celowo prosta: gui odpowiada za widoki, controller za przepływ, model za logikę, a database za SQLite."
        )

    def list_projects(self) -> list[ProjectSummary]:
        return self.repository.list_projects()

    def get_project(self, project_id: int) -> ProjectSummary:
        project = self.repository.get_project(project_id)
        if project is None:
            raise ValueError("Projekt nie istnieje.")
        return project

    def create_project(
        self,
        name: str,
        project_type: str,
        labels: list[dict[str, str | None]],
    ) -> ProjectSummary:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("Nazwa projektu jest wymagana.")
        if project_type not in self.PROJECT_TYPES:
            raise ValueError("Nieznany typ projektu.")
        description = f"Projekt typu {project_type.lower()} z {len(labels)} etykietami startowymi."
        return self.repository.create_project(cleaned_name, project_type, description, labels)

    def list_label_definitions(self, project_id: int) -> list[LabelDefinition]:
        return self.repository.list_label_definitions(project_id)

    def list_tasks(self, project_id: int) -> list[TaskSummary]:
        return self.repository.list_tasks(project_id)

    def get_task(self, task_id: int) -> TaskSummary:
        task = self.repository.get_task(task_id)
        if task is None:
            raise ValueError("Task nie istnieje.")
        return task

    def create_task(self, project_id: int, name: str, dataset_folder: str) -> TaskSummary:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("Nazwa taska jest wymagana.")
        dataset_path = dataset_folder.strip()
        image_paths: list[str] = []
        normalized_dataset_path: str | None = None
        if dataset_path:
            folder_path = Path(dataset_path)
            if not folder_path.exists() or not folder_path.is_dir():
                raise ValueError("Wskazany folder datasetu nie istnieje.")
            image_paths = self._collect_image_paths(folder_path)
            normalized_dataset_path = str(folder_path)
        return self.repository.create_task(project_id, cleaned_name, normalized_dataset_path, image_paths)

    def list_images(self, task_id: int) -> list[ImageRecord]:
        return self.repository.list_images(task_id)

    def list_annotations(self, image_id: int) -> list[AnnotationRecord]:
        return self.repository.list_annotations_for_image(image_id)

    def add_annotation(self, image_id: int, label_definition_id: int) -> AnnotationRecord:
        label = self.repository.get_label_definition(label_definition_id)
        if label is None:
            raise ValueError("Nie można znaleźć wybranej etykiety.")
        return self.repository.add_annotation(
            image_id=image_id,
            label_definition_id=label.id,
            label_name=label.name,
            label_type=label.label_type,
            source="manual",
        )

    def auto_label_image(self, project_id: int, image_id: int) -> AnnotationRecord:
        labels = self.list_label_definitions(project_id)
        if not labels:
            raise ValueError("Najpierw dodaj definicję etykiety do projektu.")
        existing = {annotation.label_name for annotation in self.list_annotations(image_id)}
        chosen = next((label for label in labels if label.name not in existing), labels[0])
        return self.repository.add_annotation(
            image_id=image_id,
            label_definition_id=chosen.id,
            label_name=chosen.name,
            label_type=chosen.label_type,
            source="model",
        )

    def toggle_annotation_visibility(self, annotation_id: int, current_visible: bool) -> None:
        self.repository.update_annotation_visibility(annotation_id, not current_visible)

    def delete_annotation(self, annotation_id: int) -> None:
        self.repository.delete_annotation(annotation_id)

    def delete_image(self, image_id: int) -> None:
        self.repository.delete_image(image_id)

    def merge_projects(self, source_project_id: int, target_project_id: int) -> None:
        self.repository.merge_projects(source_project_id, target_project_id)

    def merge_tasks(self, source_task_id: int, target_task_id: int) -> None:
        self.repository.merge_tasks(source_task_id, target_task_id)

    def load_session(self) -> SessionState:
        return self.repository.load_session()

    def save_session(self, state: SessionState) -> None:
        self.repository.save_session(state)

    def export_project(
        self,
        project_id: int,
        export_folder: str,
        export_format: str,
        split_train: int,
        split_valid: int,
        split_test: int,
        include_images: bool,
    ) -> dict[str, str | int]:
        project = self.get_project(project_id)
        if not export_folder.strip():
            raise ValueError("Wskaż folder docelowy eksportu.")
        export_root = Path(export_folder)
        export_root.mkdir(parents=True, exist_ok=True)

        tasks = self.list_tasks(project_id)
        labels = self.list_label_definitions(project_id)
        records: list[dict[str, object]] = []
        for task in tasks:
            for image in self.list_images(task.id):
                records.append(
                    {
                        "task": task,
                        "image": image,
                        "annotations": self.list_annotations(image.id),
                    }
                )

        split_names = self._build_split_assignment(records, split_train, split_valid, split_test)
        if export_format == "COCO (JSON)":
            self._export_coco(export_root, project, labels, records, split_names, include_images)
        elif export_format == "YOLO (TXT)":
            self._export_yolo(export_root, project, labels, records, split_names, include_images)
        else:
            self._export_pascal_voc(export_root, project, records, split_names, include_images)

        summary = {
            "project": project.name,
            "format": export_format,
            "image_count": len(records),
            "annotation_count": sum(len(record["annotations"]) for record in records),
            "output_folder": str(export_root),
        }
        (export_root / "export_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return summary

    def _collect_image_paths(self, folder_path: Path) -> list[str]:
        return [
            str(path)
            for path in sorted(folder_path.iterdir())
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_IMAGE_EXTENSIONS
        ]

    def _build_split_assignment(
        self,
        records: list[dict[str, object]],
        split_train: int,
        split_valid: int,
        split_test: int,
    ) -> list[str]:
        total = len(records)
        if total == 0:
            return []
        train_count = round(total * split_train / 100)
        valid_count = round(total * split_valid / 100)
        if train_count + valid_count > total:
            valid_count = max(0, total - train_count)
        test_count = total - train_count - valid_count
        counts = {
            "train": train_count,
            "valid": valid_count,
            "test": test_count,
        }
        split_names: list[str] = []
        for split_name, count in counts.items():
            split_names.extend([split_name] * count)
        while len(split_names) < total:
            split_names.append("test")
        return split_names[:total]

    def _export_coco(
        self,
        export_root: Path,
        project: ProjectSummary,
        labels: list[LabelDefinition],
        records: list[dict[str, object]],
        split_names: list[str],
        include_images: bool,
    ) -> None:
        images_payload: list[dict[str, object]] = []
        annotations_payload: list[dict[str, object]] = []
        categories = [
            {"id": index + 1, "name": label.name, "type": label.label_type}
            for index, label in enumerate(labels)
        ]
        category_lookup = {label.name: index + 1 for index, label in enumerate(labels)}
        annotation_id = 1
        for index, record in enumerate(records, start=1):
            task = record["task"]
            image = record["image"]
            annotations = record["annotations"]
            split_name = split_names[index - 1]
            exported_name = self._make_exported_filename(task.name, image.file_path, index)
            images_payload.append(
                {
                    "id": image.id,
                    "file_name": exported_name,
                    "original_path": image.file_path,
                    "task": task.name,
                    "split": split_name,
                }
            )
            for annotation in annotations:
                annotations_payload.append(
                    {
                        "id": annotation_id,
                        "image_id": image.id,
                        "category_id": category_lookup.get(annotation.label_name, 0),
                        "label_name": annotation.label_name,
                        "label_type": annotation.label_type,
                        "source": annotation.source,
                        "visible": annotation.is_visible,
                    }
                )
                annotation_id += 1
            if include_images:
                self._copy_image_if_possible(export_root / "images" / split_name / exported_name, image.file_path)

        payload = {
            "info": {"project": project.name, "description": project.description},
            "categories": categories,
            "images": images_payload,
            "annotations": annotations_payload,
        }
        (export_root / "coco_annotations.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _export_yolo(
        self,
        export_root: Path,
        project: ProjectSummary,
        labels: list[LabelDefinition],
        records: list[dict[str, object]],
        split_names: list[str],
        include_images: bool,
    ) -> None:
        names = [label.name for label in labels]
        dataset_yaml = (
            f"path: {export_root}\n"
            "train: images/train\n"
            "val: images/valid\n"
            "test: images/test\n"
            f"nc: {len(names)}\n"
            f"names: {names}\n"
            f"project: {project.name}\n"
        )
        (export_root / "dataset.yaml").write_text(dataset_yaml, encoding="utf-8")
        for index, record in enumerate(records, start=1):
            task = record["task"]
            image = record["image"]
            annotations = record["annotations"]
            split_name = split_names[index - 1]
            exported_name = self._make_exported_filename(task.name, image.file_path, index)
            label_file = export_root / "labels" / split_name / f"{Path(exported_name).stem}.txt"
            label_file.parent.mkdir(parents=True, exist_ok=True)
            lines = []
            for annotation in annotations:
                class_id = names.index(annotation.label_name) if annotation.label_name in names else -1
                lines.append(f"{class_id} 0.5 0.5 1.0 1.0 # {annotation.label_name} [{annotation.label_type}] {annotation.source}")
            if not lines:
                lines.append("# no labels")
            label_file.write_text("\n".join(lines), encoding="utf-8")
            if include_images:
                self._copy_image_if_possible(export_root / "images" / split_name / exported_name, image.file_path)

    def _export_pascal_voc(
        self,
        export_root: Path,
        project: ProjectSummary,
        records: list[dict[str, object]],
        split_names: list[str],
        include_images: bool,
    ) -> None:
        manifest: list[dict[str, str]] = []
        for index, record in enumerate(records, start=1):
            task = record["task"]
            image = record["image"]
            annotations = record["annotations"]
            split_name = split_names[index - 1]
            exported_name = self._make_exported_filename(task.name, image.file_path, index)

            annotation_root = ET.Element("annotation")
            ET.SubElement(annotation_root, "folder").text = split_name
            ET.SubElement(annotation_root, "filename").text = exported_name
            ET.SubElement(annotation_root, "project").text = project.name
            ET.SubElement(annotation_root, "task").text = task.name
            for annotation in annotations:
                object_node = ET.SubElement(annotation_root, "object")
                ET.SubElement(object_node, "name").text = annotation.label_name
                ET.SubElement(object_node, "type").text = annotation.label_type
                ET.SubElement(object_node, "source").text = annotation.source

            xml_path = export_root / "labels" / split_name / f"{Path(exported_name).stem}.xml"
            xml_path.parent.mkdir(parents=True, exist_ok=True)
            xml_path.write_text(
                ET.tostring(annotation_root, encoding="unicode"),
                encoding="utf-8",
            )
            manifest.append({"file": exported_name, "split": split_name, "task": task.name})
            if include_images:
                self._copy_image_if_possible(export_root / "images" / split_name / exported_name, image.file_path)

        (export_root / "pascal_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _copy_image_if_possible(self, destination: Path, image_path: str) -> None:
        source_path = Path(image_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source_path.exists():
            shutil.copy2(source_path, destination)

    def _make_exported_filename(self, task_name: str, image_path: str, index: int) -> str:
        safe_task_name = re.sub(r"[^A-Za-z0-9_-]+", "_", task_name).strip("_").lower() or "task"
        source = Path(image_path)
        safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", source.stem).strip("_").lower() or f"image_{index}"
        suffix = source.suffix.lower() or ".png"
        return f"{safe_task_name}_{index:04d}_{safe_stem}{suffix}"