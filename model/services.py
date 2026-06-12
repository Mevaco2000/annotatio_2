from __future__ import annotations

import csv
import importlib
import json
import os
import re
import shutil
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from database.repositories import AppRepository
from model.entities import LabelTemplate, SessionState
from model.settings import AppSettings, build_settings_description

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import torch
except ImportError:
    torch = None

try:
    tf = importlib.import_module("tensorflow")
except ImportError:
    tf = None

try:
    from ultralytics import YOLO as UltralyticsYOLO
except ImportError:
    UltralyticsYOLO = None

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None


class AppService:
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
    VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
    PYTORCH_MODEL_EXTENSIONS = {".pt", ".pth", ".ckpt", ".ts", ".jit", ".torchscript"}
    TENSORFLOW_MODEL_EXTENSIONS = {".h5", ".keras", ".tflite"}
    MODEL_EXTENSIONS = {".onnx"} | PYTORCH_MODEL_EXTENSIONS | TENSORFLOW_MODEL_EXTENSIONS
    SUPPORTED_IMAGE_EXTENSIONS = IMAGE_EXTENSIONS
    LABEL_TYPES = [
        "Bounding box",
        "Segmentacja (maska)",
        "Skeleton",
        "Polygon",
        "Point",
        "Polyline",
        "Klasyfikacja",
    ]
    PROJECT_TYPES = ["Klasyfikacja", "Wykrywanie"]
    MODEL_INFERENCE_OPTIONS = {
        "classification": "Klasyfikacja",
        "detection": "Detekcja obiektow",
        "pose": "Pose / Keypointy",
        "segmentation": "Segmentacja",
    }
    MODEL_RUNTIME_OPTIONS = {
        "auto": "Auto (wykryj implementacje)",
        "onnx": "ONNX / OpenCV DNN",
        "tensorflow": "TensorFlow",
        "ultralytics": "Ultralytics YOLO",
        "torchscript": "TorchScript",
        "pytorch": "PyTorch",
    }
    DATASET_IMPORT_FORMATS = [
        "COCO-like JSON",
        "COCO",
        "COCO Keypoints",
        "Pascal VOC",
        "ImageNet",
        "YOLO Pose 1.0",
    ]
    GENERIC_EXPORT_FORMATS = [
        "COCO-like JSON",
        "CSV",
    ]
    SPECIALIZED_EXPORT_FORMATS = [
        "YOLO",
        "Ultralytics YOLO Detection",
        "Ultralytics YOLO Segmentation",
        "COCO",
        "COCO Keypoints",
        "Pascal VOC",
        "ImageNet",
        "YOLO Pose 1.0",
    ]
    EXPORT_FORMATS = GENERIC_EXPORT_FORMATS + SPECIALIZED_EXPORT_FORMATS
    EXPORT_FORMAT_DETAILS = {
        "COCO-like JSON": {
            "summary": "Pojedynczy plik annotations_coco.json z sekcjami images/categories/annotations i geometrią w stylu COCO + raw_definition.",
            "structure": "root/annotations_coco.json\nroot/train/images/... (opcjonalnie)\nroot/valid/images/... (opcjonalnie)\nroot/test/images/... (opcjonalnie)",
        },
        "CSV": {
            "summary": "Płaski plik annotations.csv, jedna linia na adnotację, dobry do Excela i analiz tabelarycznych.",
            "structure": "root/annotations.csv\nroot/train/images/... (opcjonalnie)\nroot/valid/images/... (opcjonalnie)\nroot/test/images/... (opcjonalnie)",
        },
        "YOLO": {
            "summary": "Darknet YOLO dla bounding boxów. Tworzy obj.names, obj.data, train.txt/valid.txt i foldery obj_train_data / obj_valid_data.",
            "structure": "root/obj.data\nroot/obj.names\nroot/train.txt\nroot/valid.txt\nroot/obj_train_data/*.txt + obrazy\nroot/obj_valid_data/*.txt + obrazy",
        },
        "Ultralytics YOLO Detection": {
            "summary": "Ultralytics YOLO Detection dla bounding boxów. data.yaml, listy subsetów oraz obrazy/etykiety w images/<split> i labels/<split>.",
            "structure": "root/data.yaml\nroot/train.txt\nroot/valid.txt\nroot/test.txt\nroot/images/train/*\nroot/labels/train/*",
        },
        "Ultralytics YOLO Segmentation": {
            "summary": "Ultralytics YOLO Segmentation dla polygonów i masek. Każda linia etykiety zawiera klasę i kolejne punkty obrysu.",
            "structure": "root/data.yaml\nroot/train.txt\nroot/valid.txt\nroot/test.txt\nroot/images/train/*\nroot/labels/train/*.txt",
        },
        "COCO": {
            "summary": "Klasyczny eksport COCO instances dla bboxów oraz segmentacji. Osobny plik annotations/instances_<split>.json dla każdego splitu.",
            "structure": "root/images/train/*\nroot/images/valid/*\nroot/images/test/*\nroot/annotations/instances_train.json\nroot/annotations/instances_valid.json\nroot/annotations/instances_test.json",
        },
        "COCO Keypoints": {
            "summary": "Eksport COCO person_keypoints dla skeletonów i punktów. Każdy split dostaje własny plik person_keypoints_<split>.json.",
            "structure": "root/images/train/*\nroot/images/valid/*\nroot/images/test/*\nroot/annotations/person_keypoints_train.json\nroot/annotations/person_keypoints_valid.json\nroot/annotations/person_keypoints_test.json",
        },
        "Pascal VOC": {
            "summary": "Eksport Pascal VOC XML dla projektów bbox-only. Tworzy JPEGImages, Annotations, ImageSets/Main i labelmap.txt.",
            "structure": "root/JPEGImages/*\nroot/Annotations/*.xml\nroot/ImageSets/Main/default.txt\nroot/ImageSets/Main/train.txt\nroot/ImageSets/Main/valid.txt\nroot/labelmap.txt",
        },
        "ImageNet": {
            "summary": "Eksport klasyfikacyjny. Obrazy trafiają do katalogów nazwanych etykietami, a synsets.txt oraz pliki splitów opisują mapowanie klas.",
            "structure": "root/synsets.txt\nroot/train.txt\nroot/valid.txt\nroot/test.txt\nroot/<label_name>/*",
        },
        "YOLO Pose 1.0": {
            "summary": "Ultralytics YOLO Pose dla skeletonów i punktów. Linie etykiet zawierają bbox oraz sekwencję keypointów z visibility.",
            "structure": "root/data.yaml\nroot/train.txt\nroot/valid.txt\nroot/test.txt\nroot/images/train/*\nroot/labels/train/*.txt",
        },
    }

    def __init__(self, repository: AppRepository, projects_root: Path | None = None) -> None:
        self.repository = repository
        self.projects_root = Path(projects_root) if projects_root is not None else Path.cwd() / "projects"

    def get_default_projects_root(self) -> str:
        return str(self.projects_root)

    def get_start_description(self) -> str:
        return "Jeszcze sie buduje tej"

    def get_settings_description(self) -> str:
        return build_settings_description(
            AppSettings(
                projects_root=str(self.projects_root),
            )
        )

    def get_info_description(self) -> str:
        return "Jeszcze sie buduje tej"

    def get_available_export_formats(self, project_id: int) -> list[str]:
        project = self.get_project(project_id)
        labels = self.repository.list_label_templates(project_id)
        label_types = {label.label_type for label in labels}

        formats = list(self.GENERIC_EXPORT_FORMATS)
        formats.extend(self._get_project_specific_export_formats(project.project_type, label_types))

        ordered_unique_formats: list[str] = []
        seen: set[str] = set()
        for export_format in formats:
            if export_format in seen:
                continue
            ordered_unique_formats.append(export_format)
            seen.add(export_format)
        return ordered_unique_formats

    @classmethod
    def _get_project_specific_export_formats(cls, project_type: str, label_types: set[str]) -> list[str]:
        if not label_types:
            return []

        if project_type == "Klasyfikacja":
            if label_types <= {"Klasyfikacja"}:
                return ["ImageNet"]
            return []

        if label_types <= {"Bounding box"}:
            return ["YOLO", "Ultralytics YOLO Detection", "COCO", "Pascal VOC"]
        if label_types <= {"Polygon", "Segmentacja (maska)"}:
            return ["Ultralytics YOLO Segmentation", "COCO"]
        if label_types <= {"Bounding box", "Polygon", "Segmentacja (maska)"}:
            return ["COCO"]
        if label_types <= {"Skeleton", "Point"}:
            return ["COCO Keypoints", "YOLO Pose 1.0"]
        return []

    @classmethod
    def get_export_format_details(cls, export_format: str) -> dict[str, str]:
        return cls.EXPORT_FORMAT_DETAILS.get(
            export_format,
            {
                "summary": "Brak dodatkowego opisu dla wybranego formatu.",
                "structure": "root/...",
            },
        )

    def list_projects(self):
        return self.repository.list_projects()

    def create_project(
        self,
        name: str,
        project_type: str,
        labels: list[LabelTemplate],
        storage_folder: str | None = None,
    ) -> int:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Nazwa projektu nie moze byc pusta.")
        if project_type not in self.PROJECT_TYPES:
            raise ValueError("Nieznany typ projektu.")
        if not labels:
            raise ValueError("Projekt musi miec przynajmniej jedna etykiete.")

        base_folder = self._resolve_projects_root(storage_folder)
        project_folder = self._build_project_storage_path(base_folder, clean_name)
        project_folder.mkdir(parents=True, exist_ok=False)

        try:
            stored_labels: list[LabelTemplate] = []
            for index, label in enumerate(labels, start=1):
                label_name = label.name.strip()
                if not label_name:
                    raise ValueError("Kazda etykieta musi miec nazwe.")
                if label.label_type not in self.LABEL_TYPES:
                    raise ValueError(f"Nieznany typ etykiety: {label.label_type}")

                preview_path = self._store_label_preview(
                    project_folder,
                    label.preview_image_path,
                    index,
                    label_name,
                )
                stored_labels.append(
                    LabelTemplate(
                        id=None,
                        name=label_name,
                        label_type=label.label_type,
                        preview_image_path=preview_path,
                        preview_definition=label.preview_definition,
                    )
                )

            project_id = self.repository.create_project(
                clean_name,
                project_type,
                stored_labels,
                str(project_folder),
            )
            self._write_project_manifest(project_folder, project_id, clean_name, project_type, stored_labels)
            return project_id
        except sqlite3.IntegrityError as error:
            shutil.rmtree(project_folder, ignore_errors=True)
            raise ValueError("Projekt o tej nazwie juz istnieje.") from error
        except Exception:
            shutil.rmtree(project_folder, ignore_errors=True)
            raise

    def get_project(self, project_id: int):
        project = self.repository.get_project(project_id)
        if project is None:
            raise ValueError("Nie znaleziono projektu.")
        return project

    def list_tasks(self, project_id: int):
        return self.repository.list_tasks(project_id)

    def create_task(
        self,
        project_id: int,
        task_name: str,
        dataset_folder: str,
        image_paths: list[str] | None = None,
        video_path: str | None = None,
        frame_stride: int = 30,
        import_mode: str = "folder",
        dataset_format: str = "",
    ) -> int:
        clean_name = task_name.strip()
        if not clean_name:
            raise ValueError("Nazwa taska nie moze byc pusta.")

        clean_folder = dataset_folder.strip()
        clean_video_path = video_path.strip() if video_path else ""
        if import_mode == "images" and image_paths:
            resolved_image_paths = self._validate_explicit_image_paths(image_paths)
            common_path = Path(os.path.commonpath(resolved_image_paths))
            dataset_path = common_path if common_path.is_dir() else common_path.parent
            return self.repository.create_task(project_id, clean_name, str(dataset_path), resolved_image_paths)

        if import_mode == "video" and clean_video_path:
            extracted_frames = self._extract_video_frames(project_id, clean_name, clean_video_path, frame_stride)
            return self.repository.create_task(project_id, clean_name, clean_video_path, extracted_frames)

        if import_mode == "dataset":
            if dataset_format not in self.DATASET_IMPORT_FORMATS:
                raise ValueError("Wybierz obslugiwany format datasetu do importu.")
            if not clean_folder:
                raise ValueError("Wskaz folder datasetu do importu.")
            return self._create_task_from_dataset(project_id, clean_name, clean_folder, dataset_format)

        if clean_folder:
            folder = Path(clean_folder)
            if not folder.exists() or not folder.is_dir():
                raise ValueError("Wskazany folder z datasetem nie istnieje.")
            resolved_image_paths = self._collect_image_paths_from_folder(folder)
            if not resolved_image_paths:
                raise ValueError("W wybranym folderze nie ma obslugiwanych obrazow.")
            return self.repository.create_task(project_id, clean_name, clean_folder or None, resolved_image_paths)

        raise ValueError("Wybierz folder datasetu, zdjęcia albo plik wideo do importu.")

    def _create_task_from_dataset(self, project_id: int, task_name: str, dataset_folder: str, dataset_format: str) -> int:
        dataset_root = Path(dataset_folder)
        if not dataset_root.exists() or not dataset_root.is_dir():
            raise ValueError("Wskazany folder datasetu nie istnieje.")

        labels = self.repository.list_label_templates(project_id)
        imported_items = self._load_dataset_import_items(dataset_root, dataset_format, labels)
        if not imported_items:
            raise ValueError("Nie znaleziono obrazow w wybranym datasecie.")

        normalized_items = [
            {
                "image_path": str(Path(str(item["image_path"])).resolve()),
                "annotations": list(item.get("annotations", [])),
            }
            for item in imported_items
        ]

        task_id = self.repository.create_task(
            project_id,
            task_name,
            str(dataset_root),
            [item["image_path"] for item in normalized_items],
        )
        try:
            images = self.repository.list_images(task_id)
            image_id_by_path = {str(Path(image.file_path).resolve()): image.id for image in images}
            for item in normalized_items:
                image_id = image_id_by_path.get(str(Path(item["image_path"]).resolve()))
                if image_id is None:
                    continue
                for annotation in item["annotations"]:
                    self._store_annotation(
                        image_id=image_id,
                        label_template_id=int(annotation["label_template_id"]),
                        note=str(annotation.get("note", "")),
                        annotation_definition=annotation.get("annotation_definition"),
                        source="import",
                    )
            return task_id
        except Exception:
            self.repository.delete_task(task_id)
            raise

    def _collect_image_paths_from_folder(self, folder: Path) -> list[str]:
        return [
            str(path)
            for path in sorted(folder.rglob("*"))
            if path.is_file() and path.suffix.lower() in self.IMAGE_EXTENSIONS
        ]

    def _validate_explicit_image_paths(self, image_paths: list[str]) -> list[str]:
        resolved_paths: list[str] = []
        for raw_path in image_paths:
            path = Path(raw_path)
            if not path.exists() or not path.is_file():
                raise ValueError(f"Nie znaleziono wybranego pliku: {raw_path}")
            if path.suffix.lower() not in self.IMAGE_EXTENSIONS:
                raise ValueError(f"Plik nie jest obslugiwanym obrazem: {path.name}")
            resolved_paths.append(str(path))
        if not resolved_paths:
            raise ValueError("Wybierz przynajmniej jedno zdjęcie do importu.")
        return resolved_paths

    def _extract_video_frames(self, project_id: int, task_name: str, video_path: str, frame_stride: int) -> list[str]:
        if frame_stride < 1:
            raise ValueError("Odstęp między klatkami musi być dodatni.")
        source_path = Path(video_path)
        if not source_path.exists() or not source_path.is_file():
            raise ValueError("Wskazany plik wideo nie istnieje.")
        if source_path.suffix.lower() not in self.VIDEO_EXTENSIONS:
            raise ValueError("Nieobslugiwany format wideo.")
        if cv2 is None:
            raise ValueError("Import wideo wymaga zainstalowanego pakietu opencv-python-headless.")

        project = self.get_project(project_id)
        project_folder = Path(project.storage_path) if project.storage_path else self.projects_root
        frames_dir = self._build_task_frames_path(project_folder, task_name, source_path.stem)
        frames_dir.mkdir(parents=True, exist_ok=False)

        capture = cv2.VideoCapture(str(source_path))
        if not capture.isOpened():
            shutil.rmtree(frames_dir, ignore_errors=True)
            raise ValueError("Nie udalo sie otworzyc pliku wideo.")

        saved_paths: list[str] = []
        frame_index = 0
        saved_index = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if frame_index % frame_stride == 0:
                    frame_path = frames_dir / f"frame_{saved_index:06d}.png"
                    if not cv2.imwrite(str(frame_path), frame):
                        raise ValueError("Nie udalo sie zapisac klatek z wideo.")
                    saved_paths.append(str(frame_path))
                    saved_index += 1
                frame_index += 1
        finally:
            capture.release()

        if not saved_paths:
            shutil.rmtree(frames_dir, ignore_errors=True)
            raise ValueError("Nie udalo sie wyciac zadnych klatek z wybranego wideo.")
        return saved_paths

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
        annotations = self.repository.list_annotations_for_task(task_id)
        for image in images:
            annotations.setdefault(image.id, [])
        return {
            "project": project_details,
            "task": task,
            "labels": labels,
            "images": images,
            "annotations": annotations,
        }

    def add_annotation(
        self,
        image_id: int,
        label_template_id: int,
        note: str,
        annotation_definition: dict[str, object] | None = None,
    ) -> None:
        self._store_annotation(
            image_id=image_id,
            label_template_id=label_template_id,
            note=note,
            annotation_definition=annotation_definition,
            source="manual",
        )

    def update_annotation(self, annotation_id: int, annotation_definition: dict[str, object] | None) -> None:
        annotation = self.repository.get_annotation(annotation_id)
        if annotation is None:
            raise ValueError("Nie znaleziono wybranej annotacji.")
        if annotation.label_template_id is None:
            raise ValueError("Wybrana annotacja nie ma powiazanej etykiety.")

        label = self._find_label_template(annotation.label_template_id)
        self._validate_annotation_definition(label, annotation_definition)
        self.repository.update_annotation_definition(annotation_id, annotation_definition)

    def toggle_annotation_visibility(self, annotation_id: int) -> None:
        self.repository.toggle_annotation_visibility(annotation_id)

    def delete_annotation(self, annotation_id: int) -> None:
        self.repository.delete_annotation(annotation_id)

    def delete_image(self, image_id: int) -> None:
        self.repository.delete_image(image_id)

    def delete_project(self, project_id: int) -> None:
        project = self.get_project(project_id)
        self.repository.delete_project(project_id)

        if project.storage_path:
            project_folder = Path(project.storage_path)
            if project_folder.exists() and project_folder.is_dir():
                shutil.rmtree(project_folder, ignore_errors=True)

    def delete_task(self, task_id: int) -> None:
        task = self._find_task(task_id)
        project = self.get_project(task.project_id)
        managed_import_roots: set[Path] = set()

        if project.storage_path:
            imports_root = Path(project.storage_path) / "task_imports"
            if imports_root.exists():
                for image in self.repository.list_images(task_id):
                    image_path = Path(image.file_path)
                    try:
                        image_path.relative_to(imports_root)
                    except ValueError:
                        continue
                    managed_import_roots.add(image_path.parent)

        self.repository.delete_task(task_id)

        for managed_root in sorted(managed_import_roots, key=lambda path: len(path.parts), reverse=True):
            shutil.rmtree(managed_root, ignore_errors=True)

    def auto_label_image(
        self,
        image_id: int,
        image_path: str,
        project_type: str,
        project_labels: list[LabelTemplate],
        config: dict[str, object],
    ) -> int:
        mode_label = str(config.get("mode") or "")
        mode_key = next(
            (key for key, label in self.MODEL_INFERENCE_OPTIONS.items() if label == mode_label),
            "",
        )
        if not mode_key:
            raise ValueError("Wybrany tryb inferencji modelu nie jest obslugiwany.")

        return self.predict_annotations_for_image(
            image_id=image_id,
            image_path=image_path,
            project_type=project_type,
            labels=project_labels,
            inference_mode=mode_key,
            model_path=str(config.get("model_path") or ""),
            labels_path=str(config.get("labels_path") or "") or None,
            runtime_preference=str(config.get("runtime") or "auto"),
            confidence_threshold=float(config.get("confidence_threshold") or 0.25),
            iou_threshold=float(config.get("iou_threshold") or 0.45),
            input_width=int(config.get("input_width") or 640),
            input_height=int(config.get("input_height") or 640),
        )

    @classmethod
    def get_model_runtime_labels_for_path(cls, model_path: str | None) -> list[str]:
        candidate_path = Path(model_path or "")
        suffix = candidate_path.suffix.casefold()
        if suffix == ".onnx":
            return [cls.MODEL_RUNTIME_OPTIONS["auto"], cls.MODEL_RUNTIME_OPTIONS["onnx"]]
        if suffix in cls.TENSORFLOW_MODEL_EXTENSIONS or cls._is_tensorflow_saved_model_path(candidate_path):
            return [cls.MODEL_RUNTIME_OPTIONS["auto"], cls.MODEL_RUNTIME_OPTIONS["tensorflow"]]
        if suffix in cls.PYTORCH_MODEL_EXTENSIONS:
            return [
                cls.MODEL_RUNTIME_OPTIONS["auto"],
                cls.MODEL_RUNTIME_OPTIONS["ultralytics"],
                cls.MODEL_RUNTIME_OPTIONS["torchscript"],
                cls.MODEL_RUNTIME_OPTIONS["pytorch"],
            ]
        return [cls.MODEL_RUNTIME_OPTIONS["auto"]]

    @classmethod
    def get_model_runtime_key_from_label(cls, runtime_label: str) -> str:
        for key, label in cls.MODEL_RUNTIME_OPTIONS.items():
            if label == runtime_label:
                return key
        return "auto"

    @classmethod
    def _is_tensorflow_saved_model_path(cls, model_path: Path) -> bool:
        return model_path.exists() and model_path.is_dir() and (model_path / "saved_model.pb").exists()

    def get_available_model_inference_modes(
        self,
        project_type: str,
        labels: list[LabelTemplate],
    ) -> list[str]:
        return [label for _mode, label in self.get_supported_model_inference_options(project_type, labels)]

    def get_supported_model_inference_options(self, project_type: str, labels: list[LabelTemplate]) -> list[tuple[str, str]]:
        label_types = {label.label_type for label in labels}
        options: list[tuple[str, str]] = []
        if project_type == "Klasyfikacja" and label_types <= {"Klasyfikacja"} and labels:
            options.append(("classification", self.MODEL_INFERENCE_OPTIONS["classification"]))
        if project_type == "Wykrywanie" and label_types <= {"Bounding box"} and labels:
            options.append(("detection", self.MODEL_INFERENCE_OPTIONS["detection"]))
        if project_type == "Wykrywanie" and label_types <= {"Skeleton", "Point"} and labels:
            pose_keypoint_count = self._get_supported_pose_keypoint_count(labels)
            if pose_keypoint_count is not None:
                options.append(("pose", self.MODEL_INFERENCE_OPTIONS["pose"]))
        if project_type == "Wykrywanie" and label_types <= {"Polygon", "Segmentacja (maska)"} and labels:
            options.append(("segmentation", self.MODEL_INFERENCE_OPTIONS["segmentation"]))
        return options

    def predict_annotations_for_image(
        self,
        image_id: int,
        image_path: str,
        project_type: str,
        labels: list[LabelTemplate],
        inference_mode: str,
        model_path: str,
        labels_path: str | None,
        runtime_preference: str,
        confidence_threshold: float,
        iou_threshold: float,
        input_width: int,
        input_height: int,
    ) -> int:
        if cv2 is None:
            raise ValueError("Inferencja modelu wymaga zainstalowanego pakietu opencv-python-headless.")
        if not model_path.strip():
            raise ValueError("Wybierz plik modelu.")

        image_file = Path(image_path)
        if not image_file.exists() or not image_file.is_file():
            raise ValueError("Nie znaleziono aktualnie annotowanego obrazu.")

        model_file = Path(model_path)
        if not model_file.exists() or not model_file.is_file():
            raise ValueError("Nie znaleziono wybranego pliku modelu.")

        model_runtime = self._resolve_model_runtime(model_file)
        runtime_preference = (runtime_preference or "auto").strip().casefold()
        if model_runtime == "onnx" and runtime_preference not in {"", "auto", "onnx"}:
            raise ValueError("Dla plikow .onnx dostepna jest tylko implementacja ONNX / OpenCV DNN.")
        if model_runtime == "tensorflow" and runtime_preference not in {"", "auto", "tensorflow"}:
            raise ValueError("Dla modeli TensorFlow dostepna jest tylko implementacja TensorFlow.")
        if model_runtime == "pytorch" and runtime_preference in {"onnx", "tensorflow"}:
            raise ValueError("Implementacja ONNX / OpenCV DNN ani TensorFlow nie obsluguja plikow .pt/.pth/.ts/.jit/.ckpt.")

        supported_modes = {mode for mode, _label in self.get_supported_model_inference_options(project_type, labels)}
        if inference_mode not in supported_modes:
            raise ValueError("Aktualny projekt nie wspiera wybranego trybu inferencji modelu.")

        if input_width < 1 or input_height < 1:
            raise ValueError("Rozmiar wejścia modelu musi być dodatni.")

        class_names = self._load_model_class_names(labels, labels_path)
        image = cv2.imread(str(image_file))
        if image is None:
            raise ValueError("Nie udalo sie wczytac aktualnego obrazu do inferencji modelu.")

        self._clear_model_annotations(image_id)
        if inference_mode == "classification":
            if model_runtime == "onnx":
                net = cv2.dnn.readNetFromONNX(str(model_file))
                predicted_label = self._predict_classification_label(
                    net=net,
                    image=image,
                    labels=labels,
                    class_names=class_names,
                    input_width=input_width,
                    input_height=input_height,
                )
            elif model_runtime == "tensorflow":
                predicted_label = self._predict_tensorflow_classification_label(
                    model_path=str(model_file),
                    image=image,
                    labels=labels,
                    class_names=class_names,
                    runtime_preference=runtime_preference,
                    confidence_threshold=confidence_threshold,
                    iou_threshold=iou_threshold,
                    input_width=input_width,
                    input_height=input_height,
                )
            else:
                predicted_label = self._predict_pytorch_classification_label(
                    model_path=str(model_file),
                    image=image,
                    labels=labels,
                    class_names=class_names,
                    runtime_preference=runtime_preference,
                    confidence_threshold=confidence_threshold,
                    iou_threshold=iou_threshold,
                    input_width=input_width,
                    input_height=input_height,
                )
            self.repository.add_annotation(
                image_id=image_id,
                label_template_id=predicted_label.id or 0,
                label_name=predicted_label.name,
                label_type=predicted_label.label_type,
                annotation_definition=None,
                source="model",
                note=f"Predykcja modelu {model_file.name}",
            )
            return 1

        if model_runtime == "onnx":
            net = cv2.dnn.readNetFromONNX(str(model_file))
            if inference_mode == "detection":
                predictions = self._predict_yolo_detection_annotations(
                    net=net,
                    image=image,
                    labels=labels,
                    class_names=class_names,
                    confidence_threshold=confidence_threshold,
                    iou_threshold=iou_threshold,
                    input_width=input_width,
                    input_height=input_height,
                )
            elif inference_mode == "pose":
                predictions = self._predict_yolo_pose_annotations(
                    net=net,
                    image=image,
                    labels=labels,
                    class_names=class_names,
                    confidence_threshold=confidence_threshold,
                    iou_threshold=iou_threshold,
                    input_width=input_width,
                    input_height=input_height,
                )
            elif inference_mode == "segmentation":
                predictions = self._predict_yolo_segmentation_annotations(
                    net=net,
                    image=image,
                    labels=labels,
                    class_names=class_names,
                    confidence_threshold=confidence_threshold,
                    iou_threshold=iou_threshold,
                    input_width=input_width,
                    input_height=input_height,
                )
            else:
                raise ValueError("Wybrany tryb inferencji modelu nie jest obslugiwany.")
        elif model_runtime == "tensorflow":
            if inference_mode == "detection":
                predictions = self._predict_tensorflow_detection_annotations(
                    model_path=str(model_file),
                    image=image,
                    labels=labels,
                    class_names=class_names,
                    runtime_preference=runtime_preference,
                    confidence_threshold=confidence_threshold,
                    iou_threshold=iou_threshold,
                    input_width=input_width,
                    input_height=input_height,
                )
            elif inference_mode == "pose":
                predictions = self._predict_tensorflow_pose_annotations(
                    model_path=str(model_file),
                    image=image,
                    labels=labels,
                    class_names=class_names,
                    runtime_preference=runtime_preference,
                    confidence_threshold=confidence_threshold,
                    iou_threshold=iou_threshold,
                    input_width=input_width,
                    input_height=input_height,
                )
            elif inference_mode == "segmentation":
                predictions = self._predict_tensorflow_segmentation_annotations(
                    model_path=str(model_file),
                    image=image,
                    labels=labels,
                    class_names=class_names,
                    runtime_preference=runtime_preference,
                    confidence_threshold=confidence_threshold,
                    iou_threshold=iou_threshold,
                    input_width=input_width,
                    input_height=input_height,
                )
            else:
                raise ValueError("Wybrany tryb inferencji modelu nie jest obslugiwany.")
        else:
            if inference_mode == "detection":
                predictions = self._predict_pytorch_detection_annotations(
                    model_path=str(model_file),
                    image=image,
                    labels=labels,
                    class_names=class_names,
                    runtime_preference=runtime_preference,
                    confidence_threshold=confidence_threshold,
                    iou_threshold=iou_threshold,
                    input_width=input_width,
                    input_height=input_height,
                )
            elif inference_mode == "pose":
                predictions = self._predict_pytorch_pose_annotations(
                    model_path=str(model_file),
                    image=image,
                    labels=labels,
                    class_names=class_names,
                    runtime_preference=runtime_preference,
                    confidence_threshold=confidence_threshold,
                    iou_threshold=iou_threshold,
                    input_width=input_width,
                    input_height=input_height,
                )
            elif inference_mode == "segmentation":
                predictions = self._predict_pytorch_segmentation_annotations(
                    model_path=str(model_file),
                    image=image,
                    labels=labels,
                    class_names=class_names,
                    runtime_preference=runtime_preference,
                    confidence_threshold=confidence_threshold,
                    iou_threshold=iou_threshold,
                    input_width=input_width,
                    input_height=input_height,
                )
            else:
                raise ValueError("Wybrany tryb inferencji modelu nie jest obslugiwany.")
        if not predictions:
            return 0

        for label_template, annotation_definition, confidence in predictions:
            self.repository.add_annotation(
                image_id=image_id,
                label_template_id=label_template.id or 0,
                label_name=label_template.name,
                label_type=label_template.label_type,
                annotation_definition=annotation_definition,
                source="model",
                note=f"Predykcja modelu {model_file.name} ({confidence:.2f})",
            )
        return len(predictions)

    def _resolve_model_runtime(self, model_path: Path) -> str:
        suffix = model_path.suffix.casefold()
        if suffix == ".onnx":
            return "onnx"
        if suffix in self.TENSORFLOW_MODEL_EXTENSIONS or self._is_tensorflow_saved_model_path(model_path):
            return "tensorflow"
        if suffix in self.PYTORCH_MODEL_EXTENSIONS:
            return "pytorch"
        raise ValueError(
            "Obslugiwane sa pliki modeli: .onnx, .pt, .pth, .ckpt, .ts, .jit, .torchscript, .h5, .keras, .tflite oraz katalog SavedModel."
        )

    def _clear_model_annotations(self, image_id: int) -> None:
        for annotation in self.repository.list_annotations(image_id):
            if annotation.source == "model":
                self.repository.delete_annotation(annotation.id)

    def _load_model_class_names(self, project_labels: list[LabelTemplate], labels_path: str | None) -> list[str] | None:
        if labels_path is None or not labels_path.strip():
            return None
        labels_file = Path(labels_path)
        if not labels_file.exists() or not labels_file.is_file():
            raise ValueError("Nie znaleziono pliku klas modelu.")
        class_names = [line.strip() for line in labels_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not class_names:
            raise ValueError("Plik klas modelu jest pusty.")
        project_names = {label.name.casefold() for label in project_labels}
        missing_names = [name for name in class_names if name.casefold() not in project_names]
        if missing_names:
            raise ValueError(
                "Plik klas modelu zawiera etykiety, ktorych nie ma w projekcie. "
                f"Otrzymano: {', '.join(repr(name) for name in missing_names)}."
            )
        return class_names

    def _resolve_model_label_by_index(
        self,
        labels: list[LabelTemplate],
        class_index: int,
        class_names: list[str] | None,
    ) -> LabelTemplate:
        if class_names is not None:
            if class_index < 0 or class_index >= len(class_names):
                raise ValueError(f"Model zwrocil indeks klasy {class_index}, ktorego nie ma w pliku klas.")
            class_name = class_names[class_index]
            label_lookup = self._build_import_label_lookup(labels)
            return self._resolve_import_label(label_lookup, class_name)
        if class_index < 0 or class_index >= len(labels):
            raise ValueError(
                "Model zwrocil indeks klasy spoza zakresu etykiet projektu. "
                f"Otrzymano: {class_index}. Oczekiwano: 0..{max(len(labels) - 1, 0)}."
            )
        return labels[class_index]

    def _predict_classification_label(
        self,
        net,
        image: np.ndarray,
        labels: list[LabelTemplate],
        class_names: list[str] | None,
        input_width: int,
        input_height: int,
    ) -> LabelTemplate:
        blob = cv2.dnn.blobFromImage(image, scalefactor=1.0 / 255.0, size=(input_width, input_height), swapRB=True, crop=False)
        net.setInput(blob)
        outputs = net.forward()
        scores = np.array(outputs).reshape(-1)
        if scores.size == 0:
            raise ValueError("Model klasyfikacyjny nie zwrocil zadnych wynikow.")
        class_index = int(np.argmax(scores))
        return self._resolve_model_label_by_index(labels, class_index, class_names)

    def _predict_yolo_detection_annotations(
        self,
        net,
        image: np.ndarray,
        labels: list[LabelTemplate],
        class_names: list[str] | None,
        confidence_threshold: float,
        iou_threshold: float,
        input_width: int,
        input_height: int,
    ) -> list[tuple[LabelTemplate, dict[str, object], float]]:
        blob = cv2.dnn.blobFromImage(image, scalefactor=1.0 / 255.0, size=(input_width, input_height), swapRB=True, crop=False)
        net.setInput(blob)
        outputs = net.forward()
        predictions = np.array(outputs)
        if predictions.ndim == 3 and predictions.shape[0] == 1:
            predictions = predictions[0]
        if predictions.ndim != 2:
            raise ValueError("Model detekcyjny zwrocil nieobslugiwany format wynikow.")

        expected_class_count = len(class_names) if class_names is not None else len(labels)
        if predictions.shape[1] < 4 and predictions.shape[0] >= 4:
            predictions = predictions.T
        if predictions.shape[1] < 4:
            raise ValueError("Model detekcyjny nie zwrocil poprawnych bboxow.")
        if predictions.shape[1] >= predictions.shape[0] and predictions.shape[0] in {expected_class_count + 4, expected_class_count + 5}:
            predictions = predictions.T

        image_height, image_width = image.shape[:2]
        boxes: list[list[int]] = []
        confidences: list[float] = []
        label_templates: list[LabelTemplate] = []

        for row in predictions:
            row_values = row.astype(np.float32).flatten()
            if row_values.size < 4 + expected_class_count:
                continue

            if row_values.size >= 5 + expected_class_count:
                objectness = float(row_values[4])
                class_scores = row_values[5 : 5 + expected_class_count]
                class_id = int(np.argmax(class_scores))
                confidence = float(objectness * class_scores[class_id])
            else:
                class_scores = row_values[4 : 4 + expected_class_count]
                class_id = int(np.argmax(class_scores))
                confidence = float(class_scores[class_id])
            if confidence < confidence_threshold:
                continue

            center_x, center_y, width, height = [float(value) for value in row_values[:4]]
            x_min = max(0.0, center_x - width / 2)
            y_min = max(0.0, center_y - height / 2)
            x_max = min(float(input_width), center_x + width / 2)
            y_max = min(float(input_height), center_y + height / 2)
            scale_x = image_width / max(float(input_width), 1.0)
            scale_y = image_height / max(float(input_height), 1.0)
            abs_x = x_min * scale_x
            abs_y = y_min * scale_y
            abs_w = max(1.0, (x_max - x_min) * scale_x)
            abs_h = max(1.0, (y_max - y_min) * scale_y)

            boxes.append([int(round(abs_x)), int(round(abs_y)), int(round(abs_w)), int(round(abs_h))])
            confidences.append(confidence)
            label_templates.append(self._resolve_model_label_by_index(labels, class_id, class_names))

        if not boxes:
            return []

        kept_indices = cv2.dnn.NMSBoxes(boxes, confidences, confidence_threshold, iou_threshold)
        if len(kept_indices) == 0:
            return []

        normalized_predictions: list[tuple[LabelTemplate, dict[str, object], float]] = []
        for raw_index in kept_indices:
            index = int(raw_index[0] if isinstance(raw_index, (list, tuple, np.ndarray)) else raw_index)
            x_pos, y_pos, width, height = boxes[index]
            normalized_predictions.append(
                (
                    label_templates[index],
                    {
                        "type": "Bounding box",
                        "points": [
                            {"x": round(x_pos / max(image_width, 1), 6), "y": round(y_pos / max(image_height, 1), 6)},
                            {
                                "x": round((x_pos + width) / max(image_width, 1), 6),
                                "y": round((y_pos + height) / max(image_height, 1), 6),
                            },
                        ],
                    },
                    confidences[index],
                )
            )
        return normalized_predictions

    def _predict_yolo_pose_annotations(
        self,
        net,
        image: np.ndarray,
        labels: list[LabelTemplate],
        class_names: list[str] | None,
        confidence_threshold: float,
        iou_threshold: float,
        input_width: int,
        input_height: int,
    ) -> list[tuple[LabelTemplate, dict[str, object], float]]:
        pose_keypoint_count = self._get_supported_pose_keypoint_count(labels)
        if pose_keypoint_count is None:
            raise ValueError(
                "YOLO Pose wymaga etykiet typu Skeleton albo Point z taka sama liczba keypointow w calym projekcie."
            )

        blob = cv2.dnn.blobFromImage(image, scalefactor=1.0 / 255.0, size=(input_width, input_height), swapRB=True, crop=False)
        net.setInput(blob)
        outputs = net.forward()
        predictions = np.array(outputs)
        if predictions.ndim == 3 and predictions.shape[0] == 1:
            predictions = predictions[0]
        if predictions.ndim != 2:
            raise ValueError("Model YOLO Pose zwrocil nieobslugiwany format wynikow.")

        expected_class_count = len(class_names) if class_names is not None else len(labels)
        keypoint_value_count = pose_keypoint_count * 3
        minimum_columns = 4 + expected_class_count + keypoint_value_count
        if predictions.shape[1] < minimum_columns and predictions.shape[0] >= minimum_columns:
            predictions = predictions.T
        if predictions.shape[1] >= predictions.shape[0] and predictions.shape[0] in {
            minimum_columns,
            minimum_columns + 1,
        }:
            predictions = predictions.T
        if predictions.shape[1] < minimum_columns:
            raise ValueError(
                "Model YOLO Pose nie zwrocil oczekiwanej liczby kolumn dla bboxow, klas i keypointow."
            )

        image_height, image_width = image.shape[:2]
        scale_x = image_width / max(float(input_width), 1.0)
        scale_y = image_height / max(float(input_height), 1.0)
        boxes: list[list[int]] = []
        confidences: list[float] = []
        label_templates: list[LabelTemplate] = []
        annotation_definitions: list[dict[str, object]] = []

        for row in predictions:
            row_values = row.astype(np.float32).flatten()
            if row_values.size < minimum_columns:
                continue

            if row_values.size >= minimum_columns + 1:
                objectness = float(row_values[4])
                class_scores = row_values[5 : 5 + expected_class_count]
                class_id = int(np.argmax(class_scores))
                confidence = float(objectness * class_scores[class_id])
                keypoint_start = 5 + expected_class_count
            else:
                class_scores = row_values[4 : 4 + expected_class_count]
                class_id = int(np.argmax(class_scores))
                confidence = float(class_scores[class_id])
                keypoint_start = 4 + expected_class_count
            if confidence < confidence_threshold:
                continue

            label_template = self._resolve_model_label_by_index(labels, class_id, class_names)
            expected_points = self._get_expected_pose_keypoint_count(label_template, pose_keypoint_count)
            if expected_points != pose_keypoint_count:
                raise ValueError(
                    f"Model YOLO Pose zwrocil {pose_keypoint_count} keypointow, ale etykieta '{label_template.name}' oczekuje {expected_points}."
                )

            keypoint_values = row_values[keypoint_start : keypoint_start + keypoint_value_count]
            if keypoint_values.size < keypoint_value_count:
                continue
            points: list[dict[str, object]] = []
            for index in range(pose_keypoint_count):
                offset = index * 3
                keypoint_x = float(keypoint_values[offset]) * scale_x
                keypoint_y = float(keypoint_values[offset + 1]) * scale_y
                visibility_score = float(keypoint_values[offset + 2])
                is_visible = visibility_score >= confidence_threshold if 0.0 <= visibility_score <= 1.0 else visibility_score > 0.0
                point_payload: dict[str, object] = {
                    "x": round(min(1.0, max(0.0, keypoint_x / max(image_width, 1))), 6) if is_visible else 0.0,
                    "y": round(min(1.0, max(0.0, keypoint_y / max(image_height, 1))), 6) if is_visible else 0.0,
                }
                if not is_visible:
                    point_payload["visibility"] = 0
                points.append(point_payload)

            center_x, center_y, width, height = [float(value) for value in row_values[:4]]
            x_min = max(0.0, center_x - width / 2)
            y_min = max(0.0, center_y - height / 2)
            x_max = min(float(input_width), center_x + width / 2)
            y_max = min(float(input_height), center_y + height / 2)
            abs_x = x_min * scale_x
            abs_y = y_min * scale_y
            abs_w = max(1.0, (x_max - x_min) * scale_x)
            abs_h = max(1.0, (y_max - y_min) * scale_y)

            annotation_definition: dict[str, object] = {"type": label_template.label_type, "points": points}
            if label_template.label_type == "Skeleton":
                annotation_definition["point_count"] = len(points)
            boxes.append([int(round(abs_x)), int(round(abs_y)), int(round(abs_w)), int(round(abs_h))])
            confidences.append(confidence)
            label_templates.append(label_template)
            annotation_definitions.append(annotation_definition)

        if not boxes:
            return []

        kept_indices = cv2.dnn.NMSBoxes(boxes, confidences, confidence_threshold, iou_threshold)
        if len(kept_indices) == 0:
            return []

        normalized_predictions: list[tuple[LabelTemplate, dict[str, object], float]] = []
        for raw_index in kept_indices:
            index = int(raw_index[0] if isinstance(raw_index, (list, tuple, np.ndarray)) else raw_index)
            normalized_predictions.append((label_templates[index], annotation_definitions[index], confidences[index]))
        return normalized_predictions

    def _predict_yolo_segmentation_annotations(
        self,
        net,
        image: np.ndarray,
        labels: list[LabelTemplate],
        class_names: list[str] | None,
        confidence_threshold: float,
        iou_threshold: float,
        input_width: int,
        input_height: int,
    ) -> list[tuple[LabelTemplate, dict[str, object], float]]:
        blob = cv2.dnn.blobFromImage(image, scalefactor=1.0 / 255.0, size=(input_width, input_height), swapRB=True, crop=False)
        net.setInput(blob)
        prediction_rows, mask_prototypes = self._extract_yolo_segmentation_outputs(
            net,
            len(class_names) if class_names is not None else len(labels),
        )

        image_height, image_width = image.shape[:2]
        scale_x = image_width / max(float(input_width), 1.0)
        scale_y = image_height / max(float(input_height), 1.0)
        boxes: list[list[int]] = []
        confidences: list[float] = []
        label_templates: list[LabelTemplate] = []
        mask_coefficients: list[np.ndarray] = []

        expected_class_count = len(class_names) if class_names is not None else len(labels)
        mask_dimension = int(mask_prototypes.shape[0])
        for row in prediction_rows:
            row_values = row.astype(np.float32).flatten()
            minimum_columns = 4 + expected_class_count + mask_dimension
            if row_values.size < minimum_columns:
                continue

            if row_values.size >= minimum_columns + 1:
                objectness = float(row_values[4])
                class_scores = row_values[5 : 5 + expected_class_count]
                class_id = int(np.argmax(class_scores))
                confidence = float(objectness * class_scores[class_id])
                mask_start = 5 + expected_class_count
            else:
                class_scores = row_values[4 : 4 + expected_class_count]
                class_id = int(np.argmax(class_scores))
                confidence = float(class_scores[class_id])
                mask_start = 4 + expected_class_count
            if confidence < confidence_threshold:
                continue

            center_x, center_y, width, height = [float(value) for value in row_values[:4]]
            x_min = max(0.0, center_x - width / 2)
            y_min = max(0.0, center_y - height / 2)
            x_max = min(float(input_width), center_x + width / 2)
            y_max = min(float(input_height), center_y + height / 2)
            abs_x = x_min * scale_x
            abs_y = y_min * scale_y
            abs_w = max(1.0, (x_max - x_min) * scale_x)
            abs_h = max(1.0, (y_max - y_min) * scale_y)

            boxes.append([int(round(abs_x)), int(round(abs_y)), int(round(abs_w)), int(round(abs_h))])
            confidences.append(confidence)
            label_templates.append(self._resolve_model_label_by_index(labels, class_id, class_names))
            mask_coefficients.append(row_values[mask_start : mask_start + mask_dimension])

        if not boxes:
            return []

        kept_indices = cv2.dnn.NMSBoxes(boxes, confidences, confidence_threshold, iou_threshold)
        if len(kept_indices) == 0:
            return []

        normalized_predictions: list[tuple[LabelTemplate, dict[str, object], float]] = []
        for raw_index in kept_indices:
            index = int(raw_index[0] if isinstance(raw_index, (list, tuple, np.ndarray)) else raw_index)
            polygon_points = self._decode_yolo_segmentation_points(
                mask_prototypes=mask_prototypes,
                mask_coefficients=mask_coefficients[index],
                bbox=boxes[index],
                image_width=image_width,
                image_height=image_height,
            )
            if len(polygon_points) < 3:
                continue
            label_template = label_templates[index]
            normalized_predictions.append(
                (
                    label_template,
                    {"type": label_template.label_type, "points": polygon_points},
                    confidences[index],
                )
            )
        return normalized_predictions

    def _get_supported_pose_keypoint_count(self, labels: list[LabelTemplate]) -> int | None:
        counts: set[int] = set()
        for label in labels:
            if label.label_type == "Point":
                counts.add(1)
                continue
            if label.label_type != "Skeleton":
                continue
            preview_definition = label.preview_definition if isinstance(label.preview_definition, dict) else None
            preview_points = preview_definition.get("points", []) if preview_definition else []
            if isinstance(preview_points, list) and preview_points:
                counts.add(len(preview_points))
        if len(counts) != 1:
            return None
        return next(iter(counts))

    def _extract_yolo_segmentation_outputs(
        self,
        net,
        expected_class_count: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        output_names = list(net.getUnconnectedOutLayersNames())
        if not output_names:
            raise ValueError("Model YOLO Segmentation nie ma zdefiniowanych wyjsc inferencji.")

        raw_outputs = net.forward(output_names)
        if isinstance(raw_outputs, np.ndarray):
            tensors = [np.array(raw_outputs)]
        else:
            tensors = [np.array(output) for output in raw_outputs]

        prototype_tensor: np.ndarray | None = None
        prediction_tensor: np.ndarray | None = None
        for tensor in tensors:
            if tensor.ndim == 4:
                prototype_tensor = tensor
            elif tensor.ndim in {2, 3}:
                if prediction_tensor is None or tensor.size > prediction_tensor.size:
                    prediction_tensor = tensor
        if prototype_tensor is None or prediction_tensor is None:
            raise ValueError("Model YOLO Segmentation nie zwrocil oczekiwanych wyjsc detekcji i masek.")

        mask_prototypes = prototype_tensor[0] if prototype_tensor.ndim == 4 and prototype_tensor.shape[0] == 1 else prototype_tensor
        if mask_prototypes.ndim != 3:
            raise ValueError("Model YOLO Segmentation zwrocil nieprawidlowy tensor prototypow maski.")

        prediction_rows = prediction_tensor[0] if prediction_tensor.ndim == 3 and prediction_tensor.shape[0] == 1 else prediction_tensor
        if prediction_rows.ndim != 2:
            raise ValueError("Model YOLO Segmentation zwrocil nieobslugiwany tensor detekcji.")

        mask_dimension = int(mask_prototypes.shape[0])
        minimum_columns = 4 + expected_class_count + mask_dimension
        if prediction_rows.shape[1] < minimum_columns and prediction_rows.shape[0] >= minimum_columns:
            prediction_rows = prediction_rows.T
        if prediction_rows.shape[1] >= prediction_rows.shape[0] and prediction_rows.shape[0] in {
            minimum_columns,
            minimum_columns + 1,
        }:
            prediction_rows = prediction_rows.T
        if prediction_rows.shape[1] < minimum_columns:
            raise ValueError("Model YOLO Segmentation nie zwrocil wymaganych kolumn bbox + klasy + maski.")
        return prediction_rows, mask_prototypes.astype(np.float32)

    def _decode_yolo_segmentation_points(
        self,
        mask_prototypes: np.ndarray,
        mask_coefficients: np.ndarray,
        bbox: list[int],
        image_width: int,
        image_height: int,
    ) -> list[dict[str, float]]:
        mask_logits = np.tensordot(mask_coefficients.astype(np.float32), mask_prototypes, axes=(0, 0))
        mask_probabilities = 1.0 / (1.0 + np.exp(-mask_logits))
        resized_mask = cv2.resize(mask_probabilities, (image_width, image_height), interpolation=cv2.INTER_LINEAR)

        x_pos, y_pos, width, height = bbox
        x0 = max(0, min(image_width - 1, x_pos))
        y0 = max(0, min(image_height - 1, y_pos))
        x1 = max(x0 + 1, min(image_width, x_pos + width))
        y1 = max(y0 + 1, min(image_height, y_pos + height))
        binary_mask = np.zeros((image_height, image_width), dtype=np.uint8)
        binary_mask[y0:y1, x0:x1] = (resized_mask[y0:y1, x0:x1] >= 0.5).astype(np.uint8) * 255

        contours, _hierarchy = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []
        contour = max(contours, key=cv2.contourArea)
        if cv2.contourArea(contour) <= 1.0:
            return []

        perimeter = cv2.arcLength(contour, True)
        simplified = cv2.approxPolyDP(contour, 0.005 * perimeter, True)
        if len(simplified) < 3:
            simplified = contour
        points: list[dict[str, float]] = []
        for raw_point in simplified.reshape(-1, 2):
            points.append(
                {
                    "x": round(min(1.0, max(0.0, float(raw_point[0]) / max(image_width, 1))), 6),
                    "y": round(min(1.0, max(0.0, float(raw_point[1]) / max(image_height, 1))), 6),
                }
            )
        return points

    def _predict_pytorch_classification_label(
        self,
        model_path: str,
        image: np.ndarray,
        labels: list[LabelTemplate],
        class_names: list[str] | None,
        runtime_preference: str,
        confidence_threshold: float,
        iou_threshold: float,
        input_width: int,
        input_height: int,
    ) -> LabelTemplate:
        runtime_name, model = self._load_pytorch_model(model_path, runtime_preference)
        if runtime_name == "ultralytics":
            result = self._run_ultralytics_model(
                model,
                image,
                input_width=input_width,
                input_height=input_height,
                confidence_threshold=confidence_threshold,
                iou_threshold=iou_threshold,
            )
            probs = getattr(result, "probs", None)
            if probs is None:
                raise ValueError("Model .pt nie zwrocil wynikow klasyfikacji.")
            class_index = int(getattr(probs, "top1", 0))
            return self._resolve_model_label_by_index(labels, class_index, class_names)

        output = self._run_pytorch_model(model, image, input_width, input_height)
        scores = self._extract_classification_scores(output)
        if scores.size == 0:
            raise ValueError("Model .pt nie zwrocil zadnych wynikow klasyfikacji.")
        class_index = int(np.argmax(scores))
        return self._resolve_model_label_by_index(labels, class_index, class_names)

    def _predict_pytorch_detection_annotations(
        self,
        model_path: str,
        image: np.ndarray,
        labels: list[LabelTemplate],
        class_names: list[str] | None,
        runtime_preference: str,
        confidence_threshold: float,
        iou_threshold: float,
        input_width: int,
        input_height: int,
    ) -> list[tuple[LabelTemplate, dict[str, object], float]]:
        runtime_name, model = self._load_pytorch_model(model_path, runtime_preference)
        if runtime_name == "ultralytics":
            return self._predict_ultralytics_detection_annotations(
                model,
                image,
                labels,
                class_names,
                confidence_threshold,
                iou_threshold,
                input_width,
                input_height,
            )

        prediction = self._extract_first_prediction(self._run_pytorch_model(model, image, input_width, input_height))
        boxes = self._to_numpy_array(prediction.get("boxes"))
        if boxes is None or boxes.ndim != 2 or boxes.shape[1] < 4:
            raise ValueError(
                "Model .pt nie zwrocil boxow w formacie detection. "
                f"Oczekiwano slownika z kluczem 'boxes' o ksztalcie [N,4+]. Szczegoly wyjscia: {self._describe_prediction_mapping(prediction)}"
            )
        scores = self._to_numpy_array(prediction.get("scores"))
        raw_labels = self._to_numpy_array(prediction.get("labels"))

        image_height, image_width = image.shape[:2]
        predictions: list[tuple[LabelTemplate, dict[str, object], float]] = []
        for index, box in enumerate(boxes):
            confidence = float(scores[index]) if scores is not None and index < len(scores) else 1.0
            if confidence < confidence_threshold:
                continue
            raw_label = int(raw_labels[index]) if raw_labels is not None and index < len(raw_labels) else 0
            label_template = self._resolve_model_label_from_raw_index(labels, raw_label, class_names)
            bbox_points = self._normalize_xyxy_box(box, image_width, image_height)
            predictions.append((label_template, {"type": "Bounding box", "points": bbox_points}, confidence))
        return predictions

    def _predict_pytorch_pose_annotations(
        self,
        model_path: str,
        image: np.ndarray,
        labels: list[LabelTemplate],
        class_names: list[str] | None,
        runtime_preference: str,
        confidence_threshold: float,
        iou_threshold: float,
        input_width: int,
        input_height: int,
    ) -> list[tuple[LabelTemplate, dict[str, object], float]]:
        runtime_name, model = self._load_pytorch_model(model_path, runtime_preference)
        if runtime_name == "ultralytics":
            return self._predict_ultralytics_pose_annotations(
                model,
                image,
                labels,
                class_names,
                confidence_threshold,
                iou_threshold,
                input_width,
                input_height,
            )

        prediction = self._extract_first_prediction(self._run_pytorch_model(model, image, input_width, input_height))
        keypoints = self._to_numpy_array(prediction.get("keypoints"))
        if keypoints is None:
            raise ValueError(
                "Model .pt nie zwrocil keypointow dla trybu pose. "
                f"Oczekiwano slownika z kluczem 'keypoints'. Szczegoly wyjscia: {self._describe_prediction_mapping(prediction)}"
            )
        if keypoints.ndim == 4 and keypoints.shape[0] == 1:
            keypoints = keypoints[0]
        if keypoints.ndim != 3 or keypoints.shape[2] < 2:
            raise ValueError(
                "Model .pt zwrocil nieobslugiwany format keypointow. "
                f"Oczekiwano tensora [N,K,2+] lub [1,N,K,2+]. Otrzymano: {self._describe_value(keypoints)}"
            )

        scores = self._to_numpy_array(prediction.get("scores"))
        raw_labels = self._to_numpy_array(prediction.get("labels"))
        image_height, image_width = image.shape[:2]
        predictions: list[tuple[LabelTemplate, dict[str, object], float]] = []
        for index, instance_keypoints in enumerate(keypoints):
            confidence = float(scores[index]) if scores is not None and index < len(scores) else 1.0
            if confidence < confidence_threshold:
                continue
            raw_label = int(raw_labels[index]) if raw_labels is not None and index < len(raw_labels) else 0
            label_template = self._resolve_model_label_from_raw_index(labels, raw_label, class_names)
            expected_count = self._get_expected_pose_keypoint_count(label_template, len(instance_keypoints))
            if label_template.label_type == "Point":
                instance_keypoints = instance_keypoints[:1]
            elif len(instance_keypoints) != expected_count:
                raise ValueError(
                    f"Model .pt zwrocil {len(instance_keypoints)} keypointow, ale etykieta '{label_template.name}' oczekuje {expected_count}."
                )

            points: list[dict[str, object]] = []
            for point_index, raw_point in enumerate(instance_keypoints[:expected_count]):
                raw_x = float(raw_point[0])
                raw_y = float(raw_point[1])
                raw_visibility = float(raw_point[2]) if len(raw_point) >= 3 else 1.0
                point_x, point_y = self._normalize_point_coordinates(raw_x, raw_y, image_width, image_height)
                is_visible = raw_visibility >= confidence_threshold if 0.0 <= raw_visibility <= 1.0 else raw_visibility > 0.0
                point_payload: dict[str, object] = {
                    "x": point_x if is_visible else 0.0,
                    "y": point_y if is_visible else 0.0,
                }
                if not is_visible:
                    point_payload["visibility"] = 0
                points.append(point_payload)

            annotation_definition: dict[str, object] = {"type": label_template.label_type, "points": points}
            if label_template.label_type == "Skeleton":
                annotation_definition["point_count"] = len(points)
            predictions.append((label_template, annotation_definition, confidence))
        return predictions

    def _predict_pytorch_segmentation_annotations(
        self,
        model_path: str,
        image: np.ndarray,
        labels: list[LabelTemplate],
        class_names: list[str] | None,
        runtime_preference: str,
        confidence_threshold: float,
        iou_threshold: float,
        input_width: int,
        input_height: int,
    ) -> list[tuple[LabelTemplate, dict[str, object], float]]:
        runtime_name, model = self._load_pytorch_model(model_path, runtime_preference)
        if runtime_name == "ultralytics":
            return self._predict_ultralytics_segmentation_annotations(
                model,
                image,
                labels,
                class_names,
                confidence_threshold,
                iou_threshold,
                input_width,
                input_height,
            )

        output = self._run_pytorch_model(model, image, input_width, input_height)
        try:
            prediction = self._extract_first_prediction(output)
        except ValueError:
            prediction = None

        if prediction is not None and prediction.get("masks") is not None:
            masks = self._to_numpy_array(prediction.get("masks"))
            if masks is None:
                return []
            if masks.ndim == 4 and masks.shape[1] == 1:
                masks = masks[:, 0]
            scores = self._to_numpy_array(prediction.get("scores"))
            raw_labels = self._to_numpy_array(prediction.get("labels"))
            predictions: list[tuple[LabelTemplate, dict[str, object], float]] = []
            for index, mask in enumerate(masks):
                confidence = float(scores[index]) if scores is not None and index < len(scores) else 1.0
                if confidence < confidence_threshold:
                    continue
                raw_label = int(raw_labels[index]) if raw_labels is not None and index < len(raw_labels) else 0
                label_template = self._resolve_model_label_from_raw_index(labels, raw_label, class_names)
                polygon_points = self._mask_array_to_polygon_points(mask, image.shape[1], image.shape[0])
                if len(polygon_points) < 3:
                    continue
                predictions.append((label_template, {"type": label_template.label_type, "points": polygon_points}, confidence))
            return predictions

        semantic_scores = self._extract_semantic_segmentation_scores(output)
        class_map = np.argmax(semantic_scores, axis=0)
        predictions = []
        for raw_label in sorted(int(value) for value in np.unique(class_map)):
            if class_names is None and semantic_scores.shape[0] == len(labels) + 1 and raw_label == 0:
                continue
            mask = class_map == raw_label
            if int(np.count_nonzero(mask)) < 9:
                continue
            label_template = self._resolve_model_label_from_raw_index(labels, raw_label, class_names)
            polygon_points = self._mask_array_to_polygon_points(mask.astype(np.float32), image.shape[1], image.shape[0])
            if len(polygon_points) < 3:
                continue
            predictions.append((label_template, {"type": label_template.label_type, "points": polygon_points}, 1.0))
        return predictions

    def _predict_tensorflow_classification_label(
        self,
        model_path: str,
        image: np.ndarray,
        labels: list[LabelTemplate],
        class_names: list[str] | None,
        runtime_preference: str,
        confidence_threshold: float,
        iou_threshold: float,
        input_width: int,
        input_height: int,
    ) -> LabelTemplate:
        runtime_name, model = self._load_tensorflow_model(model_path, runtime_preference)
        output = self._run_tensorflow_model(runtime_name, model, image, input_width, input_height)
        scores = self._extract_classification_scores(output)
        if scores.size == 0:
            raise ValueError("Model TensorFlow nie zwrocil zadnych wynikow klasyfikacji.")
        class_index = int(np.argmax(scores))
        return self._resolve_model_label_by_index(labels, class_index, class_names)

    def _predict_tensorflow_detection_annotations(
        self,
        model_path: str,
        image: np.ndarray,
        labels: list[LabelTemplate],
        class_names: list[str] | None,
        runtime_preference: str,
        confidence_threshold: float,
        iou_threshold: float,
        input_width: int,
        input_height: int,
    ) -> list[tuple[LabelTemplate, dict[str, object], float]]:
        runtime_name, model = self._load_tensorflow_model(model_path, runtime_preference)
        prediction = self._extract_tensorflow_prediction(self._run_tensorflow_model(runtime_name, model, image, input_width, input_height))
        boxes = self._to_numpy_array(prediction.get("boxes"))
        if boxes is None or boxes.ndim != 2 or boxes.shape[1] < 4:
            raise ValueError(
                "Model TensorFlow nie zwrocil boxow w formacie detection. "
                f"Oczekiwano slownika z kluczem 'boxes' o ksztalcie [N,4+]. Szczegoly wyjscia: {self._describe_prediction_mapping(prediction)}"
            )
        scores = self._to_numpy_array(prediction.get("scores"))
        raw_labels = self._to_numpy_array(prediction.get("labels"))

        image_height, image_width = image.shape[:2]
        predictions: list[tuple[LabelTemplate, dict[str, object], float]] = []
        for index, box in enumerate(boxes):
            confidence = float(scores[index]) if scores is not None and index < len(scores) else 1.0
            if confidence < confidence_threshold:
                continue
            raw_label = int(raw_labels[index]) if raw_labels is not None and index < len(raw_labels) else 0
            label_template = self._resolve_model_label_from_raw_index(labels, raw_label, class_names)
            bbox_points = self._normalize_xyxy_box(box, image_width, image_height)
            predictions.append((label_template, {"type": "Bounding box", "points": bbox_points}, confidence))
        return predictions

    def _predict_tensorflow_pose_annotations(
        self,
        model_path: str,
        image: np.ndarray,
        labels: list[LabelTemplate],
        class_names: list[str] | None,
        runtime_preference: str,
        confidence_threshold: float,
        iou_threshold: float,
        input_width: int,
        input_height: int,
    ) -> list[tuple[LabelTemplate, dict[str, object], float]]:
        runtime_name, model = self._load_tensorflow_model(model_path, runtime_preference)
        prediction = self._extract_tensorflow_prediction(self._run_tensorflow_model(runtime_name, model, image, input_width, input_height))
        keypoints = self._to_numpy_array(prediction.get("keypoints"))
        if keypoints is None:
            raise ValueError(
                "Model TensorFlow nie zwrocil keypointow dla trybu pose. "
                f"Oczekiwano slownika z kluczem 'keypoints'. Szczegoly wyjscia: {self._describe_prediction_mapping(prediction)}"
            )
        if keypoints.ndim == 4 and keypoints.shape[0] == 1:
            keypoints = keypoints[0]
        if keypoints.ndim != 3 or keypoints.shape[2] < 2:
            raise ValueError(
                "Model TensorFlow zwrocil nieobslugiwany format keypointow. "
                f"Oczekiwano tensora [N,K,2+] lub [1,N,K,2+]. Otrzymano: {self._describe_value(keypoints)}"
            )

        scores = self._to_numpy_array(prediction.get("scores"))
        raw_labels = self._to_numpy_array(prediction.get("labels"))
        image_height, image_width = image.shape[:2]
        predictions: list[tuple[LabelTemplate, dict[str, object], float]] = []
        for index, instance_keypoints in enumerate(keypoints):
            confidence = float(scores[index]) if scores is not None and index < len(scores) else 1.0
            if confidence < confidence_threshold:
                continue
            raw_label = int(raw_labels[index]) if raw_labels is not None and index < len(raw_labels) else 0
            label_template = self._resolve_model_label_from_raw_index(labels, raw_label, class_names)
            expected_count = self._get_expected_pose_keypoint_count(label_template, len(instance_keypoints))
            if label_template.label_type == "Point":
                instance_keypoints = instance_keypoints[:1]
            elif len(instance_keypoints) != expected_count:
                raise ValueError(
                    f"Model TensorFlow zwrocil {len(instance_keypoints)} keypointow, ale etykieta '{label_template.name}' oczekuje {expected_count}."
                )

            points: list[dict[str, object]] = []
            for raw_point in instance_keypoints[:expected_count]:
                raw_x = float(raw_point[0])
                raw_y = float(raw_point[1])
                raw_visibility = float(raw_point[2]) if len(raw_point) >= 3 else 1.0
                point_x, point_y = self._normalize_point_coordinates(raw_x, raw_y, image_width, image_height)
                is_visible = raw_visibility >= confidence_threshold if 0.0 <= raw_visibility <= 1.0 else raw_visibility > 0.0
                point_payload: dict[str, object] = {
                    "x": point_x if is_visible else 0.0,
                    "y": point_y if is_visible else 0.0,
                }
                if not is_visible:
                    point_payload["visibility"] = 0
                points.append(point_payload)

            annotation_definition: dict[str, object] = {"type": label_template.label_type, "points": points}
            if label_template.label_type == "Skeleton":
                annotation_definition["point_count"] = len(points)
            predictions.append((label_template, annotation_definition, confidence))
        return predictions

    def _predict_tensorflow_segmentation_annotations(
        self,
        model_path: str,
        image: np.ndarray,
        labels: list[LabelTemplate],
        class_names: list[str] | None,
        runtime_preference: str,
        confidence_threshold: float,
        iou_threshold: float,
        input_width: int,
        input_height: int,
    ) -> list[tuple[LabelTemplate, dict[str, object], float]]:
        runtime_name, model = self._load_tensorflow_model(model_path, runtime_preference)
        output = self._run_tensorflow_model(runtime_name, model, image, input_width, input_height)
        try:
            prediction = self._extract_tensorflow_prediction(output)
        except ValueError:
            prediction = None

        if prediction is not None and prediction.get("masks") is not None:
            masks = self._to_numpy_array(prediction.get("masks"))
            if masks is None:
                return []
            if masks.ndim == 4 and masks.shape[1] == 1:
                masks = masks[:, 0]
            scores = self._to_numpy_array(prediction.get("scores"))
            raw_labels = self._to_numpy_array(prediction.get("labels"))
            predictions: list[tuple[LabelTemplate, dict[str, object], float]] = []
            for index, mask in enumerate(masks):
                confidence = float(scores[index]) if scores is not None and index < len(scores) else 1.0
                if confidence < confidence_threshold:
                    continue
                raw_label = int(raw_labels[index]) if raw_labels is not None and index < len(raw_labels) else 0
                label_template = self._resolve_model_label_from_raw_index(labels, raw_label, class_names)
                polygon_points = self._mask_array_to_polygon_points(mask, image.shape[1], image.shape[0])
                if len(polygon_points) < 3:
                    continue
                predictions.append((label_template, {"type": label_template.label_type, "points": polygon_points}, confidence))
            return predictions

        semantic_scores = self._extract_semantic_segmentation_scores(output)
        class_map = np.argmax(semantic_scores, axis=0)
        predictions = []
        for raw_label in sorted(int(value) for value in np.unique(class_map)):
            if class_names is None and semantic_scores.shape[0] == len(labels) + 1 and raw_label == 0:
                continue
            mask = class_map == raw_label
            if int(np.count_nonzero(mask)) < 9:
                continue
            label_template = self._resolve_model_label_from_raw_index(labels, raw_label, class_names)
            polygon_points = self._mask_array_to_polygon_points(mask.astype(np.float32), image.shape[1], image.shape[0])
            if len(polygon_points) < 3:
                continue
            predictions.append((label_template, {"type": label_template.label_type, "points": polygon_points}, 1.0))
        return predictions

    def _load_tensorflow_model(self, model_path: str, runtime_preference: str = "auto") -> tuple[str, object]:
        if tf is None:
            raise ValueError("Obsluga modeli TensorFlow wymaga zainstalowanego pakietu tensorflow.")

        runtime_preference = (runtime_preference or "auto").strip().casefold()
        if runtime_preference not in {"auto", "tensorflow"}:
            raise ValueError("Dla modeli TensorFlow dostepna jest tylko implementacja TensorFlow.")

        model_file = Path(model_path)
        try:
            if model_file.suffix.casefold() == ".tflite":
                interpreter = tf.lite.Interpreter(model_path=model_path)
                interpreter.allocate_tensors()
                return "tflite", interpreter
            if self._is_tensorflow_saved_model_path(model_file):
                saved_model = tf.saved_model.load(model_path)
                signatures = getattr(saved_model, "signatures", {})
                signature = signatures.get("serving_default") if isinstance(signatures, dict) else None
                if signature is None and signatures:
                    signature = next(iter(signatures.values()))
                if signature is not None or callable(saved_model):
                    return "savedmodel", (saved_model, signature)
                raise ValueError("katalog SavedModel nie udostepnia uruchamialnej sygnatury inferencyjnej.")

            keras_model = tf.keras.models.load_model(model_path, compile=False)
            if hasattr(keras_model, "__call__"):
                return "keras", keras_model
            raise ValueError("plik nie zawiera uruchamialnego modelu TensorFlow.")
        except Exception as error:
            raise ValueError(f"Nie udalo sie uruchomic modelu TensorFlow. {error}") from error

    def _run_tensorflow_model(self, runtime_name: str, model, image: np.ndarray, input_width: int, input_height: int):
        if tf is None:
            raise ValueError("Obsluga modeli TensorFlow wymaga zainstalowanego pakietu tensorflow.")

        if runtime_name == "tflite":
            interpreter = model
            input_details = interpreter.get_input_details()
            if not input_details:
                raise ValueError("Model TFLite nie ma zdefiniowanych wejsc inferencji.")
            input_detail = input_details[0]
            input_array = self._build_tensorflow_input_array(
                image,
                input_width,
                input_height,
                input_detail.get("dtype", np.float32),
                input_detail.get("quantization"),
            )
            interpreter.set_tensor(input_detail["index"], input_array)
            interpreter.invoke()
            output_details = interpreter.get_output_details()
            outputs = [interpreter.get_tensor(detail["index"]) for detail in output_details]
            return self._format_tflite_outputs(output_details, outputs)

        input_array = self._build_tensorflow_input_array(image, input_width, input_height, np.float32)
        input_tensor = tf.convert_to_tensor(input_array)
        if runtime_name == "savedmodel":
            saved_model, signature = model
            if signature is not None:
                structured_signature = getattr(signature, "structured_input_signature", None)
                keyword_inputs = structured_signature[1] if structured_signature is not None else {}
                if keyword_inputs:
                    input_name = next(iter(keyword_inputs))
                    return signature(**{input_name: input_tensor})
                return signature(input_tensor)
            callable_model = saved_model
        else:
            callable_model = model
        try:
            return callable_model(input_tensor, training=False)
        except TypeError:
            return callable_model(input_tensor)

    def _build_tensorflow_input_array(
        self,
        image: np.ndarray,
        input_width: int,
        input_height: int,
        dtype,
        quantization: tuple[float, int] | None = None,
    ) -> np.ndarray:
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        resized_image = cv2.resize(rgb_image, (input_width, input_height), interpolation=cv2.INTER_LINEAR)
        numpy_dtype = np.dtype(dtype)
        if np.issubdtype(numpy_dtype, np.floating):
            input_array = resized_image.astype(np.float32) / 255.0
            return np.expand_dims(input_array.astype(numpy_dtype, copy=False), axis=0)

        input_array = resized_image.astype(np.float32)
        quantization_scale = 0.0
        quantization_zero_point = 0
        if quantization is not None and len(quantization) == 2:
            quantization_scale, quantization_zero_point = quantization
        if quantization_scale:
            input_array = np.round(input_array / float(quantization_scale) + int(quantization_zero_point))
        dtype_limits = np.iinfo(numpy_dtype)
        input_array = np.clip(input_array, dtype_limits.min, dtype_limits.max).astype(numpy_dtype)
        return np.expand_dims(input_array, axis=0)

    def _format_tflite_outputs(self, output_details: list[dict[str, object]], outputs: list[object]):
        if not outputs:
            raise ValueError("Model TFLite nie zwrocil zadnych wynikow.")
        if len(outputs) == 1:
            return outputs[0]

        named_outputs: dict[str, object] = {}
        for index, (detail, value) in enumerate(zip(output_details, outputs)):
            output_name = str(detail.get("name") or f"output_{index}")
            clean_name = output_name.split(":")[0].split("/")[-1]
            named_outputs[f"output_{index}"] = value
            named_outputs[clean_name] = value

        inferred_prediction = self._infer_tensorflow_prediction_from_sequence(outputs)
        if inferred_prediction is not None:
            named_outputs.update(inferred_prediction)
        return named_outputs

    def _extract_tensorflow_prediction(self, output) -> dict[str, object]:
        candidate = output
        if isinstance(candidate, (list, tuple)):
            inferred_prediction = self._infer_tensorflow_prediction_from_sequence(candidate)
            if inferred_prediction is not None:
                return inferred_prediction
            if len(candidate) == 1:
                candidate = candidate[0]

        if not isinstance(candidate, dict):
            raise ValueError(
                "Model TensorFlow nie zwrocil obslugiwanego slownika predykcji. "
                "Aplikacja oczekuje: dict albo listy/tuple zawierajacej dict. "
                f"Rzeczywiste wyjscie modelu: {self._describe_value(output)}"
            )

        prediction: dict[str, object] = {}
        raw_boxes = candidate.get("boxes", candidate.get("detection_boxes"))
        if raw_boxes is not None:
            boxes = self._to_numpy_array(raw_boxes)
            if boxes is not None:
                boxes = self._squeeze_prediction_array(boxes)
                if "detection_boxes" in candidate:
                    boxes = self._convert_tensorflow_yxyx_boxes_to_xyxy(boxes)
                prediction["boxes"] = boxes

        raw_scores = candidate.get("scores", candidate.get("detection_scores"))
        if raw_scores is not None:
            scores = self._to_numpy_array(raw_scores)
            if scores is not None:
                prediction["scores"] = self._squeeze_prediction_array(scores)

        raw_labels = candidate.get("labels", candidate.get("classes", candidate.get("class_ids", candidate.get("detection_classes"))))
        if raw_labels is not None:
            labels = self._to_numpy_array(raw_labels)
            if labels is not None:
                prediction["labels"] = self._squeeze_prediction_array(labels)

        raw_keypoints = candidate.get("keypoints", candidate.get("detection_keypoints"))
        if raw_keypoints is not None:
            keypoints = self._to_numpy_array(raw_keypoints)
            if keypoints is not None:
                keypoints = self._squeeze_prediction_array(keypoints)
                if "detection_keypoints" in candidate:
                    keypoints = self._convert_tensorflow_yx_keypoints_to_xy(keypoints)
                prediction["keypoints"] = keypoints

        raw_masks = candidate.get("masks", candidate.get("detection_masks"))
        if raw_masks is not None:
            masks = self._to_numpy_array(raw_masks)
            if masks is not None:
                prediction["masks"] = self._squeeze_prediction_array(masks)

        if prediction:
            return prediction

        raise ValueError(
            "Model TensorFlow nie zwrocil rozpoznanego slownika predykcji dla detection/pose/segmentation. "
            f"Dostepne klucze: {', '.join(str(key) for key in candidate.keys()) or 'brak'}"
        )

    def _infer_tensorflow_prediction_from_sequence(self, output_sequence) -> dict[str, object] | None:
        arrays: list[np.ndarray] = []
        for value in output_sequence:
            array_value = self._to_numpy_array(value)
            if array_value is None:
                continue
            arrays.append(self._squeeze_prediction_array(np.array(array_value)))
        if not arrays:
            return None

        boxes = next((array for array in arrays if array.ndim == 2 and array.shape[1] >= 4), None)
        keypoints = next((array for array in arrays if array.ndim == 3 and array.shape[2] >= 2), None)
        masks = next((array for array in arrays if array.ndim in {3, 4} and array.shape[-1] not in {2, 3, 4}), None)
        vector_candidates = [array for array in arrays if array.ndim == 1]

        prediction: dict[str, object] = {}
        candidate_length = len(boxes) if boxes is not None else (len(keypoints) if keypoints is not None else None)
        if boxes is not None:
            prediction["boxes"] = self._convert_tensorflow_yxyx_boxes_to_xyxy(boxes)
        if keypoints is not None:
            prediction["keypoints"] = self._convert_tensorflow_yx_keypoints_to_xy(keypoints)
        if masks is not None:
            prediction["masks"] = masks
        if candidate_length is not None:
            score_candidates = [array for array in vector_candidates if len(array) == candidate_length]
            label_candidate = next((array for array in score_candidates if self._looks_like_class_indices(array)), None)
            score_candidate = next((array for array in score_candidates if array is not label_candidate), None)
            if label_candidate is not None:
                prediction["labels"] = label_candidate
            if score_candidate is not None:
                prediction["scores"] = score_candidate
        return prediction or None

    def _squeeze_prediction_array(self, array: np.ndarray) -> np.ndarray:
        return array[0] if array.ndim > 0 and array.shape[0] == 1 else array

    def _convert_tensorflow_yxyx_boxes_to_xyxy(self, boxes: np.ndarray) -> np.ndarray:
        boxes = np.array(boxes, dtype=np.float32)
        if boxes.ndim != 2 or boxes.shape[1] < 4:
            return boxes
        converted = boxes.copy()
        converted[:, 0] = boxes[:, 1]
        converted[:, 1] = boxes[:, 0]
        converted[:, 2] = boxes[:, 3]
        converted[:, 3] = boxes[:, 2]
        return converted

    def _convert_tensorflow_yx_keypoints_to_xy(self, keypoints: np.ndarray) -> np.ndarray:
        keypoints = np.array(keypoints, dtype=np.float32)
        if keypoints.ndim != 3 or keypoints.shape[2] < 2:
            return keypoints
        converted = keypoints.copy()
        converted[:, :, 0] = keypoints[:, :, 1]
        converted[:, :, 1] = keypoints[:, :, 0]
        return converted

    def _looks_like_class_indices(self, values: np.ndarray) -> bool:
        flattened = np.array(values, dtype=np.float32).reshape(-1)
        if flattened.size == 0 or not np.all(np.isfinite(flattened)):
            return False
        return np.allclose(flattened, np.round(flattened), atol=1e-4)

    def _load_pytorch_model(self, model_path: str, runtime_preference: str = "auto") -> tuple[str, object]:
        if torch is None:
            raise ValueError("Obsluga modeli .pt wymaga zainstalowanego pakietu torch.")

        runtime_preference = (runtime_preference or "auto").strip().casefold()
        runtime_display_name = self.MODEL_RUNTIME_OPTIONS.get(runtime_preference, runtime_preference or "auto")
        if runtime_preference not in self.MODEL_RUNTIME_OPTIONS:
            raise ValueError(f"Nieznana implementacja modelu: {runtime_display_name}.")

        runtime_errors: list[str] = []
        loader_order = ["torchscript", "ultralytics", "pytorch"] if runtime_preference == "auto" else [runtime_preference]
        for runtime_name in loader_order:
            try:
                if runtime_name == "torchscript":
                    scripted_model = torch.jit.load(model_path, map_location="cpu")
                    scripted_model.eval()
                    return "torchscript", scripted_model
                if runtime_name == "ultralytics":
                    if UltralyticsYOLO is None:
                        raise ValueError("pakiet ultralytics nie jest zainstalowany.")
                    return "ultralytics", UltralyticsYOLO(model_path)
                if runtime_name == "pytorch":
                    try:
                        loaded_model = torch.load(model_path, map_location="cpu", weights_only=False)
                    except TypeError:
                        loaded_model = torch.load(model_path, map_location="cpu")
                    candidate_model = loaded_model.get("model") if isinstance(loaded_model, dict) and "model" in loaded_model else loaded_model
                    if hasattr(candidate_model, "eval"):
                        candidate_model.eval()
                    if callable(candidate_model):
                        return "pytorch", candidate_model
                    raise ValueError("plik nie zawiera uruchamialnego modelu.")
            except Exception as error:
                runtime_errors.append(f"{self.MODEL_RUNTIME_OPTIONS[runtime_name]}: {error}")

        if runtime_preference == "auto":
            raise ValueError(
                "Nie udalo sie uruchomic modelu .pt/.pth/.ts. Sprobuj TorchScript, zgodnego modelu PyTorch albo modelu Ultralytics. "
                + " | ".join(runtime_errors)
            )
        raise ValueError(f"Nie udalo sie uruchomic modelu jako {runtime_display_name}. " + " | ".join(runtime_errors))

    def _run_pytorch_model(self, model, image: np.ndarray, input_width: int, input_height: int):
        if torch is None:
            raise ValueError("Obsluga modeli .pt wymaga zainstalowanego pakietu torch.")
        input_tensor = self._build_pytorch_input_tensor(image, input_width, input_height)
        model_device, model_dtype = self._get_pytorch_model_tensor_spec(model)
        if model_device is not None:
            if model_device.type == "cpu" and model_dtype == torch.float16 and hasattr(model, "float"):
                model = model.float()
                model_dtype = torch.float32
            input_tensor = input_tensor.to(device=model_device, dtype=model_dtype or input_tensor.dtype)
        with torch.inference_mode():
            return model(input_tensor)

    def _get_pytorch_model_tensor_spec(self, model) -> tuple[object | None, object | None]:
        if torch is None:
            return None, None

        for accessor_name in ("parameters", "buffers"):
            accessor = getattr(model, accessor_name, None)
            if accessor is None:
                continue
            try:
                first_tensor = next(accessor())
            except (StopIteration, TypeError):
                continue
            return first_tensor.device, first_tensor.dtype
        return None, None

    def _build_pytorch_input_tensor(self, image: np.ndarray, input_width: int, input_height: int):
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        resized_image = cv2.resize(rgb_image, (input_width, input_height), interpolation=cv2.INTER_LINEAR)
        image_tensor = torch.from_numpy(resized_image.astype(np.float32) / 255.0)
        return image_tensor.permute(2, 0, 1).unsqueeze(0)

    def _run_ultralytics_model(
        self,
        model,
        image: np.ndarray,
        input_width: int,
        input_height: int,
        confidence_threshold: float,
        iou_threshold: float,
    ):
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = model.predict(
            source=image_rgb,
            imgsz=max(input_width, input_height),
            conf=confidence_threshold,
            iou=iou_threshold,
            verbose=False,
            device="cpu",
        )
        if not results:
            raise ValueError("Model Ultralytics nie zwrocil zadnych wynikow.")
        return results[0]

    def _predict_ultralytics_detection_annotations(
        self,
        model,
        image: np.ndarray,
        labels: list[LabelTemplate],
        class_names: list[str] | None,
        confidence_threshold: float,
        iou_threshold: float,
        input_width: int,
        input_height: int,
    ) -> list[tuple[LabelTemplate, dict[str, object], float]]:
        result = self._run_ultralytics_model(model, image, input_width, input_height, confidence_threshold, iou_threshold)
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []
        xyxy = self._to_numpy_array(getattr(boxes, "xyxy", None))
        cls_values = self._to_numpy_array(getattr(boxes, "cls", None))
        conf_values = self._to_numpy_array(getattr(boxes, "conf", None))
        if xyxy is None:
            return []
        predictions: list[tuple[LabelTemplate, dict[str, object], float]] = []
        image_height, image_width = image.shape[:2]
        for index, box in enumerate(xyxy):
            confidence = float(conf_values[index]) if conf_values is not None and index < len(conf_values) else 1.0
            raw_label = int(cls_values[index]) if cls_values is not None and index < len(cls_values) else 0
            label_template = self._resolve_model_label_from_raw_index(labels, raw_label, class_names)
            predictions.append(
                (
                    label_template,
                    {"type": "Bounding box", "points": self._normalize_xyxy_box(box, image_width, image_height)},
                    confidence,
                )
            )
        return predictions

    def _predict_ultralytics_pose_annotations(
        self,
        model,
        image: np.ndarray,
        labels: list[LabelTemplate],
        class_names: list[str] | None,
        confidence_threshold: float,
        iou_threshold: float,
        input_width: int,
        input_height: int,
    ) -> list[tuple[LabelTemplate, dict[str, object], float]]:
        result = self._run_ultralytics_model(model, image, input_width, input_height, confidence_threshold, iou_threshold)
        boxes = getattr(result, "boxes", None)
        keypoints = getattr(result, "keypoints", None)
        if boxes is None or keypoints is None:
            return []
        cls_values = self._to_numpy_array(getattr(boxes, "cls", None))
        conf_values = self._to_numpy_array(getattr(boxes, "conf", None))
        point_values = self._to_numpy_array(getattr(keypoints, "xy", None))
        point_confidences = self._to_numpy_array(getattr(keypoints, "conf", None))
        if point_values is None:
            return []
        predictions: list[tuple[LabelTemplate, dict[str, object], float]] = []
        image_height, image_width = image.shape[:2]
        for index, instance_points in enumerate(point_values):
            confidence = float(conf_values[index]) if conf_values is not None and index < len(conf_values) else 1.0
            raw_label = int(cls_values[index]) if cls_values is not None and index < len(cls_values) else 0
            label_template = self._resolve_model_label_from_raw_index(labels, raw_label, class_names)
            expected_count = self._get_expected_pose_keypoint_count(label_template, len(instance_points))
            if label_template.label_type == "Point":
                instance_points = instance_points[:1]
            elif len(instance_points) != expected_count:
                raise ValueError(
                    f"Model .pt zwrocil {len(instance_points)} keypointow, ale etykieta '{label_template.name}' oczekuje {expected_count}."
                )

            points: list[dict[str, object]] = []
            for point_index, raw_point in enumerate(instance_points[:expected_count]):
                point_confidence = None
                if point_confidences is not None and index < len(point_confidences) and point_index < len(point_confidences[index]):
                    point_confidence = float(point_confidences[index][point_index])
                point_x, point_y = self._normalize_point_coordinates(float(raw_point[0]), float(raw_point[1]), image_width, image_height)
                is_visible = True if point_confidence is None else point_confidence >= confidence_threshold
                point_payload: dict[str, object] = {"x": point_x if is_visible else 0.0, "y": point_y if is_visible else 0.0}
                if not is_visible:
                    point_payload["visibility"] = 0
                points.append(point_payload)

            annotation_definition: dict[str, object] = {"type": label_template.label_type, "points": points}
            if label_template.label_type == "Skeleton":
                annotation_definition["point_count"] = len(points)
            predictions.append((label_template, annotation_definition, confidence))
        return predictions

    def _predict_ultralytics_segmentation_annotations(
        self,
        model,
        image: np.ndarray,
        labels: list[LabelTemplate],
        class_names: list[str] | None,
        confidence_threshold: float,
        iou_threshold: float,
        input_width: int,
        input_height: int,
    ) -> list[tuple[LabelTemplate, dict[str, object], float]]:
        result = self._run_ultralytics_model(model, image, input_width, input_height, confidence_threshold, iou_threshold)
        boxes = getattr(result, "boxes", None)
        masks = getattr(result, "masks", None)
        if boxes is None or masks is None:
            return []
        cls_values = self._to_numpy_array(getattr(boxes, "cls", None))
        conf_values = self._to_numpy_array(getattr(boxes, "conf", None))
        mask_polygons = getattr(masks, "xyn", None)
        if mask_polygons is None:
            raw_masks = self._to_numpy_array(getattr(masks, "data", None))
            if raw_masks is None:
                return []
            if raw_masks.ndim == 4 and raw_masks.shape[1] == 1:
                raw_masks = raw_masks[:, 0]
            mask_polygons = [self._mask_array_to_polygon_points(raw_mask, image.shape[1], image.shape[0]) for raw_mask in raw_masks]

        predictions: list[tuple[LabelTemplate, dict[str, object], float]] = []
        for index, polygon in enumerate(mask_polygons):
            confidence = float(conf_values[index]) if conf_values is not None and index < len(conf_values) else 1.0
            raw_label = int(cls_values[index]) if cls_values is not None and index < len(cls_values) else 0
            label_template = self._resolve_model_label_from_raw_index(labels, raw_label, class_names)
            polygon_points = self._normalize_polygon_points(polygon, image.shape[1], image.shape[0])
            if len(polygon_points) < 3:
                continue
            predictions.append((label_template, {"type": label_template.label_type, "points": polygon_points}, confidence))
        return predictions

    def _extract_classification_scores(self, output) -> np.ndarray:
        candidate = output
        if isinstance(candidate, (list, tuple)) and len(candidate) == 1:
            candidate = candidate[0]
        if isinstance(candidate, dict):
            for key in ("logits", "scores", "probabilities", "probs", "out"):
                if key in candidate:
                    candidate = candidate[key]
                    break
        scores = self._to_numpy_array(candidate)
        if scores is None:
            return np.array([], dtype=np.float32)
        return np.array(scores, dtype=np.float32).reshape(-1)

    def _extract_first_prediction(self, output) -> dict[str, object]:
        candidate = output
        if isinstance(candidate, tuple) and len(candidate) == 1:
            candidate = candidate[0]
        if isinstance(candidate, list):
            if not candidate:
                raise ValueError("Model nie zwrocil zadnych predykcji.")
            candidate = candidate[0]
        if not isinstance(candidate, dict):
            raise ValueError(
                "Model .pt nie zwrocil obslugiwanego slownika predykcji. "
                "Aplikacja oczekuje: dict albo listy/tuple zawierajacej dict. "
                f"Rzeczywiste wyjscie modelu: {self._describe_value(output)}"
            )
        return candidate

    def _describe_prediction_mapping(self, prediction: dict[str, object]) -> str:
        if not prediction:
            return "pusty slownik"
        fragments: list[str] = []
        for key, value in prediction.items():
            fragments.append(f"{key}={self._describe_value(value)}")
        return ", ".join(fragments)

    def _describe_value(self, value) -> str:
        if isinstance(value, dict):
            keys = list(value.keys())
            preview = ", ".join(str(key) for key in keys[:5])
            if len(keys) > 5:
                preview += ", ..."
            return f"dict(keys=[{preview}])"
        if isinstance(value, list):
            if not value:
                return "list(len=0)"
            return f"list(len={len(value)}, first={self._describe_value(value[0])})"
        if isinstance(value, tuple):
            if not value:
                return "tuple(len=0)"
            return f"tuple(len={len(value)}, first={self._describe_value(value[0])})"
        array_value = self._to_numpy_array(value)
        if array_value is not None:
            return f"array(shape={tuple(array_value.shape)}, dtype={array_value.dtype})"
        return type(value).__name__

    def _extract_semantic_segmentation_scores(self, output) -> np.ndarray:
        candidate = output
        if isinstance(candidate, dict) and "out" in candidate:
            candidate = candidate["out"]
        elif isinstance(candidate, (list, tuple)) and len(candidate) == 1:
            candidate = candidate[0]
        scores = self._to_numpy_array(candidate)
        if scores is None:
            raise ValueError("Model nie zwrocil map segmentacji.")
        scores = np.array(scores, dtype=np.float32)
        if scores.ndim == 4 and scores.shape[0] == 1:
            scores = scores[0]
        if scores.ndim == 3 and scores.shape[2] < scores.shape[0] and scores.shape[2] < scores.shape[1]:
            scores = np.transpose(scores, (2, 0, 1))
        if scores.ndim != 3:
            raise ValueError("Model zwrocil nieobslugiwany format map segmentacji.")
        return scores

    def _to_numpy_array(self, value) -> np.ndarray | None:
        if value is None:
            return None
        if isinstance(value, np.ndarray):
            return value
        if tf is not None and isinstance(value, tf.Tensor):
            return value.numpy()
        if torch is not None and isinstance(value, torch.Tensor):
            return value.detach().cpu().numpy()
        return np.array(value)

    def _resolve_model_label_from_raw_index(
        self,
        labels: list[LabelTemplate],
        raw_label: int,
        class_names: list[str] | None,
    ) -> LabelTemplate:
        candidate_indexes = [raw_label]
        if raw_label > 0:
            candidate_indexes.append(raw_label - 1)
        attempted_indexes: set[int] = set()
        last_error: ValueError | None = None
        for candidate_index in candidate_indexes:
            if candidate_index in attempted_indexes:
                continue
            attempted_indexes.add(candidate_index)
            try:
                return self._resolve_model_label_by_index(labels, candidate_index, class_names)
            except ValueError as error:
                last_error = error
        if last_error is not None:
            raise last_error
        raise ValueError(f"Model zwrocil nieobslugiwany indeks klasy {raw_label}.")

    def _normalize_xyxy_box(self, raw_box, image_width: int, image_height: int) -> list[dict[str, float]]:
        x0, y0, x1, y1 = [float(value) for value in raw_box[:4]]
        if max(abs(x0), abs(y0), abs(x1), abs(y1)) <= 1.5:
            normalized_x0 = min(1.0, max(0.0, x0))
            normalized_y0 = min(1.0, max(0.0, y0))
            normalized_x1 = min(1.0, max(0.0, x1))
            normalized_y1 = min(1.0, max(0.0, y1))
        else:
            normalized_x0 = min(1.0, max(0.0, x0 / max(image_width, 1)))
            normalized_y0 = min(1.0, max(0.0, y0 / max(image_height, 1)))
            normalized_x1 = min(1.0, max(0.0, x1 / max(image_width, 1)))
            normalized_y1 = min(1.0, max(0.0, y1 / max(image_height, 1)))
        x_min = min(normalized_x0, normalized_x1)
        y_min = min(normalized_y0, normalized_y1)
        x_max = max(normalized_x0, normalized_x1)
        y_max = max(normalized_y0, normalized_y1)
        return [
            {"x": round(x_min, 6), "y": round(y_min, 6)},
            {"x": round(x_max, 6), "y": round(y_max, 6)},
        ]

    def _normalize_point_coordinates(self, raw_x: float, raw_y: float, image_width: int, image_height: int) -> tuple[float, float]:
        if max(abs(raw_x), abs(raw_y)) <= 1.5:
            return round(min(1.0, max(0.0, raw_x)), 6), round(min(1.0, max(0.0, raw_y)), 6)
        return (
            round(min(1.0, max(0.0, raw_x / max(image_width, 1))), 6),
            round(min(1.0, max(0.0, raw_y / max(image_height, 1))), 6),
        )

    def _mask_array_to_polygon_points(
        self,
        mask: np.ndarray,
        image_width: int,
        image_height: int,
    ) -> list[dict[str, float]]:
        if mask.ndim == 3 and mask.shape[0] == 1:
            mask = mask[0]
        resized_mask = cv2.resize(mask.astype(np.float32), (image_width, image_height), interpolation=cv2.INTER_LINEAR)
        binary_mask = (resized_mask >= 0.5).astype(np.uint8) * 255
        contours, _hierarchy = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []
        contour = max(contours, key=cv2.contourArea)
        if cv2.contourArea(contour) <= 1.0:
            return []
        perimeter = cv2.arcLength(contour, True)
        simplified = cv2.approxPolyDP(contour, 0.005 * perimeter, True)
        if len(simplified) < 3:
            simplified = contour
        return self._normalize_polygon_points(simplified.reshape(-1, 2), image_width, image_height)

    def _normalize_polygon_points(self, polygon, image_width: int, image_height: int) -> list[dict[str, float]]:
        polygon_array = np.array(polygon, dtype=np.float32)
        if polygon_array.ndim != 2 or polygon_array.shape[1] < 2:
            return []
        if np.max(np.abs(polygon_array)) <= 1.5:
            return [
                {"x": round(min(1.0, max(0.0, float(point[0]))), 6), "y": round(min(1.0, max(0.0, float(point[1]))), 6)}
                for point in polygon_array
            ]
        return [
            {
                "x": round(min(1.0, max(0.0, float(point[0]) / max(image_width, 1))), 6),
                "y": round(min(1.0, max(0.0, float(point[1]) / max(image_height, 1))), 6),
            }
            for point in polygon_array
        ]

    def merge_projects(self, source_project_id: int, target_project_id: int) -> None:
        self.repository.merge_projects(source_project_id, target_project_id)

    def merge_tasks(self, source_task_id: int, target_task_id: int) -> None:
        self.repository.merge_tasks(source_task_id, target_task_id)

    def _find_task(self, task_id: int):
        for project in self.list_projects():
            for task in self.repository.list_tasks(project.id):
                if task.id == task_id:
                    return task
        raise ValueError("Nie znaleziono taska.")

    def export_project(
        self,
        project_id: int,
        export_format: str,
        split: dict[str, int],
        include_images: bool,
        destination_folder: str,
    ) -> str:
        available_formats = self.get_available_export_formats(project_id)
        if export_format not in available_formats:
            raise ValueError("Wybrany format nie jest zgodny z typem projektu i geometrią etykiet.")

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

        export_base = Path(destination_folder)
        export_name = f"{project.name.replace(' ', '_')}_{self._slugify(export_format)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        export_root = export_base / export_name
        suffix = 2
        while export_root.exists():
            export_root = export_base / f"{export_name}_{suffix}"
            suffix += 1
        export_root.mkdir(parents=True, exist_ok=False)

        split_names = self._build_split_assignments(image_rows, split)
        labels = self.repository.list_label_templates(project_id)
        manifest = {
            "project": {
                "id": project.id,
                "name": project.name,
                "project_type": project.project_type,
                "export_format": export_format,
            },
            "labels": [asdict(label) for label in labels],
            "items": [],
        }

        for index, item in enumerate(image_rows):
            split_name = split_names[index]
            image = item["image"]
            source_path = Path(image.file_path)
            image_width, image_height = self._get_image_size(image.file_path)
            export_image_name = f"{index + 1:06d}_{self._slugify(item['task_name'])}_{source_path.name}"

            manifest["items"].append(
                {
                    "split": split_name,
                    "task": item["task_name"],
                    "image_id": image.id,
                    "image_name": export_image_name,
                    "original_image_name": source_path.name,
                    "source_image_path": image.file_path,
                    "width": image_width,
                    "height": image_height,
                    "annotations": [asdict(annotation) for annotation in item["annotations"]],
                }
            )

        export_handlers = {
            "COCO-like JSON": self._export_coco_like_json,
            "CSV": self._export_csv,
            "YOLO": self._export_yolo,
            "Ultralytics YOLO Detection": self._export_ultralytics_yolo_detection,
            "Ultralytics YOLO Segmentation": self._export_ultralytics_yolo_segmentation,
            "COCO": self._export_coco,
            "COCO Keypoints": self._export_coco_keypoints,
            "Pascal VOC": self._export_pascal_voc,
            "ImageNet": self._export_imagenet,
            "YOLO Pose 1.0": self._export_yolo_pose,
        }

        handler = export_handlers.get(export_format)
        if handler is None:
            raise ValueError("Nieznany format eksportu.")
        handler(export_root, manifest, include_images)

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

    def _store_annotation(
        self,
        image_id: int,
        label_template_id: int,
        note: str,
        annotation_definition: dict[str, object] | None,
        source: str,
    ) -> None:
        label = self._find_label_template(label_template_id)
        self._validate_annotation_definition(label, annotation_definition)
        self.repository.add_annotation(
            image_id=image_id,
            label_template_id=label_template_id,
            label_name=label.name,
            label_type=label.label_type,
            annotation_definition=annotation_definition,
            source=source,
            note=note,
        )

    def _build_import_label_lookup(self, project_labels: list[LabelTemplate]) -> dict[str, LabelTemplate]:
        lookup: dict[str, LabelTemplate] = {}
        for label in project_labels:
            lookup[label.name] = label
            lookup[label.name.casefold()] = label
        return lookup

    def _format_expected_received(self, expected: object, received: object) -> str:
        return f"Otrzymano: {received}. Oczekiwano: {expected}."

    def _describe_project_label_names(self, label_lookup: dict[str, LabelTemplate]) -> str:
        label_names = sorted({label.name for label in label_lookup.values()}, key=lambda value: value.casefold())
        if not label_names:
            return "co najmniej jedna etykieta projektu"
        return ", ".join(f"'{label_name}'" for label_name in label_names)

    def _resolve_import_label(self, label_lookup: dict[str, LabelTemplate], label_name: str) -> LabelTemplate:
        label = label_lookup.get(label_name) or label_lookup.get(label_name.casefold())
        if label is None or label.id is None:
            raise ValueError(
                "Nie znaleziono etykiety projektu odpowiadajacej nazwie z datasetu. "
                + self._format_expected_received(
                    f"jedna z nazw projektu: {self._describe_project_label_names(label_lookup)}",
                    f"'{label_name}'",
                )
            )
        return label

    def _load_dataset_import_items(
        self,
        dataset_root: Path,
        dataset_format: str,
        project_labels: list[LabelTemplate],
    ) -> list[dict[str, object]]:
        label_lookup = self._build_import_label_lookup(project_labels)
        parsers = {
            "COCO-like JSON": self._load_coco_like_dataset,
            "COCO": self._load_coco_dataset,
            "COCO Keypoints": self._load_coco_keypoints_dataset,
            "Pascal VOC": self._load_pascal_voc_dataset,
            "ImageNet": self._load_imagenet_dataset,
            "YOLO Pose 1.0": self._load_yolo_pose_dataset,
        }
        parser = parsers.get(dataset_format)
        if parser is None:
            raise ValueError(f"Import formatu '{dataset_format}' nie jest obslugiwany.")
        return parser(dataset_root, label_lookup)

    def _load_coco_like_dataset(self, dataset_root: Path, label_lookup: dict[str, LabelTemplate]) -> list[dict[str, object]]:
        annotation_file = dataset_root / "annotations_coco.json"
        if not annotation_file.exists():
            raise ValueError("W wybranym folderze nie znaleziono pliku annotations_coco.json.")
        payload = json.loads(annotation_file.read_text(encoding="utf-8"))
        images_by_id: dict[int, dict[str, object]] = {}
        for image in payload.get("images", []):
            if not isinstance(image, dict) or not isinstance(image.get("id"), int):
                continue
            image_path = self._resolve_import_image_path(
                dataset_root,
                image.get("path"),
                image.get("file_name"),
                image.get("split"),
            )
            images_by_id[image["id"]] = {"image_path": image_path, "annotations": []}

        for annotation in payload.get("annotations", []):
            if not isinstance(annotation, dict):
                continue
            image_entry = images_by_id.get(annotation.get("image_id"))
            if image_entry is None:
                continue
            label_name = str(annotation.get("label_name") or "")
            if not label_name:
                continue
            label = self._resolve_import_label(label_lookup, label_name)
            definition = annotation.get("raw_definition") if isinstance(annotation.get("raw_definition"), dict) else None
            if definition is None and label.label_type == "Klasyfikacja":
                definition = None
            if definition is None and label.label_type != "Klasyfikacja":
                raise ValueError(
                    f"Brakuje geometrii dla etykiety '{label_name}' w COCO-like JSON. "
                    + self._format_expected_received(f"raw_definition dla typu {label.label_type}", "brak")
                )
            image_entry["annotations"].append(
                {
                    "label_template_id": label.id,
                    "annotation_definition": definition,
                    "note": str(annotation.get("note") or ""),
                }
            )

        return list(images_by_id.values())

    def _load_coco_dataset(self, dataset_root: Path, label_lookup: dict[str, LabelTemplate]) -> list[dict[str, object]]:
        annotation_files = sorted((dataset_root / "annotations").glob("instances_*.json"))
        if not annotation_files:
            raise ValueError("W wybranym folderze nie znaleziono plikow instances_<split>.json.")
        return self._load_coco_family_dataset(dataset_root, label_lookup, annotation_files, keypoints=False)

    def _load_coco_keypoints_dataset(self, dataset_root: Path, label_lookup: dict[str, LabelTemplate]) -> list[dict[str, object]]:
        annotation_files = sorted((dataset_root / "annotations").glob("person_keypoints_*.json"))
        if not annotation_files:
            raise ValueError("W wybranym folderze nie znaleziono plikow person_keypoints_<split>.json.")
        return self._load_coco_family_dataset(dataset_root, label_lookup, annotation_files, keypoints=True)

    def _load_coco_family_dataset(
        self,
        dataset_root: Path,
        label_lookup: dict[str, LabelTemplate],
        annotation_files: list[Path],
        keypoints: bool,
    ) -> list[dict[str, object]]:
        items_by_path: dict[str, dict[str, object]] = {}
        for annotation_file in annotation_files:
            split_name = annotation_file.stem.split("_")[-1]
            payload = json.loads(annotation_file.read_text(encoding="utf-8"))
            categories = {
                int(category["id"]): str(category["name"])
                for category in payload.get("categories", [])
                if isinstance(category, dict) and isinstance(category.get("id"), int)
            }
            images = {
                int(image["id"]): image
                for image in payload.get("images", [])
                if isinstance(image, dict) and isinstance(image.get("id"), int)
            }
            for image in images.values():
                image_path = self._resolve_import_image_path(
                    dataset_root,
                    None,
                    image.get("file_name"),
                    split_name,
                )
                items_by_path.setdefault(str(image_path), {"image_path": str(image_path), "annotations": []})

            for annotation in payload.get("annotations", []):
                if not isinstance(annotation, dict):
                    continue
                image_info = images.get(annotation.get("image_id"))
                label_name = categories.get(annotation.get("category_id"))
                if image_info is None or not label_name:
                    continue
                label = self._resolve_import_label(label_lookup, label_name)
                image_path = self._resolve_import_image_path(dataset_root, None, image_info.get("file_name"), split_name)
                definition = self._build_import_definition_from_coco_annotation(
                    annotation=annotation,
                    label=label,
                    image_width=int(image_info.get("width") or 0),
                    image_height=int(image_info.get("height") or 0),
                    include_keypoints=keypoints,
                )
                items_by_path.setdefault(str(image_path), {"image_path": str(image_path), "annotations": []})["annotations"].append(
                    {
                        "label_template_id": label.id,
                        "annotation_definition": definition,
                        "note": str((annotation.get("attributes") or {}).get("note") or ""),
                    }
                )
        return list(items_by_path.values())

    def _load_pascal_voc_dataset(self, dataset_root: Path, label_lookup: dict[str, LabelTemplate]) -> list[dict[str, object]]:
        annotations_dir = dataset_root / "Annotations"
        xml_files = sorted(annotations_dir.glob("*.xml"))
        if not xml_files:
            raise ValueError("W wybranym folderze nie znaleziono plikow Pascal VOC XML.")
        items: list[dict[str, object]] = []
        for xml_file in xml_files:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            filename = root.findtext("filename")
            width = int(root.findtext("size/width") or 0)
            height = int(root.findtext("size/height") or 0)
            image_path = self._resolve_import_image_path(dataset_root, None, filename, None)
            annotations: list[dict[str, object]] = []
            for obj in root.findall("object"):
                label_name = obj.findtext("name") or ""
                if not label_name:
                    continue
                label = self._resolve_import_label(label_lookup, label_name)
                if label.label_type != "Bounding box":
                    raise ValueError(
                        f"Import Pascal VOC nie moze uzyc etykiety '{label_name}'. "
                        + self._format_expected_received("Bounding box", label.label_type)
                    )
                x_min = float(obj.findtext("bndbox/xmin") or 0)
                y_min = float(obj.findtext("bndbox/ymin") or 0)
                x_max = float(obj.findtext("bndbox/xmax") or 0)
                y_max = float(obj.findtext("bndbox/ymax") or 0)
                annotations.append(
                    {
                        "label_template_id": label.id,
                        "annotation_definition": {
                            "type": "Bounding box",
                            "points": [
                                {"x": round(x_min / max(width, 1), 6), "y": round(y_min / max(height, 1), 6)},
                                {"x": round(x_max / max(width, 1), 6), "y": round(y_max / max(height, 1), 6)},
                            ],
                        },
                        "note": "",
                    }
                )
            items.append({"image_path": str(image_path), "annotations": annotations})
        return items

    def _load_imagenet_dataset(self, dataset_root: Path, label_lookup: dict[str, LabelTemplate]) -> list[dict[str, object]]:
        synsets_path = dataset_root / "synsets.txt"
        if synsets_path.exists():
            label_names = [line.strip() for line in synsets_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            class_names_by_index = {index: name for index, name in enumerate(label_names)}
            items: list[dict[str, object]] = []
            found_split = False
            for split_name in ("train", "valid", "test"):
                split_path = dataset_root / f"{split_name}.txt"
                if not split_path.exists():
                    continue
                found_split = True
                for line in split_path.read_text(encoding="utf-8").splitlines():
                    stripped_line = line.strip()
                    if not stripped_line:
                        continue
                    try:
                        relative_path, class_index_text = stripped_line.rsplit(" ", maxsplit=1)
                        class_index = int(class_index_text)
                    except ValueError as error:
                        raise ValueError(f"Nieprawidlowy wpis ImageNet: {stripped_line}") from error
                    label_name = class_names_by_index.get(class_index)
                    if label_name is None:
                        raise ValueError(f"Nie znaleziono klasy o indeksie {class_index} w synsets.txt.")
                    label = self._resolve_import_label(label_lookup, label_name)
                    if label.label_type != "Klasyfikacja":
                        raise ValueError(
                            f"Import ImageNet nie moze uzyc etykiety '{label_name}'. "
                            + self._format_expected_received("Klasyfikacja", label.label_type)
                        )
                    image_path = self._resolve_import_image_path(dataset_root, relative_path, None, None)
                    items.append(
                        {
                            "image_path": str(image_path),
                            "annotations": [
                                {
                                    "label_template_id": label.id,
                                    "annotation_definition": None,
                                    "note": "",
                                }
                            ],
                        }
                    )
            if found_split:
                return items

        items = []
        for label_name, label in sorted(
            ((name, entry) for name, entry in label_lookup.items() if name == entry.name),
            key=lambda item: item[0].casefold(),
        ):
            if label.label_type != "Klasyfikacja":
                continue
            class_dir = dataset_root / self._slugify(label_name)
            if not class_dir.exists():
                class_dir = dataset_root / label_name
            if not class_dir.exists() or not class_dir.is_dir():
                continue
            for image_path in self._collect_image_paths_from_folder(class_dir):
                items.append(
                    {
                        "image_path": image_path,
                        "annotations": [
                            {
                                "label_template_id": label.id,
                                "annotation_definition": None,
                                "note": "",
                            }
                        ],
                    }
                )
        if not items:
            raise ValueError("Nie znaleziono danych ImageNet do importu.")
        return items

    def _load_yolo_pose_dataset(self, dataset_root: Path, label_lookup: dict[str, LabelTemplate]) -> list[dict[str, object]]:
        metadata = self._read_ultralytics_data_yaml(dataset_root)
        class_names_by_index = metadata["names"]
        split_entries = self._read_ultralytics_split_entries(dataset_root, metadata)
        if not split_entries:
            raise ValueError("W wybranym folderze nie znaleziono wpisow YOLO Pose do importu.")
        items: list[dict[str, object]] = []
        for split_name, image_relative_path in split_entries:
            image_path = self._resolve_import_image_path(dataset_root, image_relative_path, None, None)
            label_path = self._resolve_ultralytics_label_path(dataset_root, split_name, image_relative_path)
            annotations: list[dict[str, object]] = []
            if label_path.exists():
                annotations = self._load_yolo_pose_annotations(label_path, label_lookup, class_names_by_index)
            items.append({"image_path": str(image_path), "annotations": annotations})
        return items

    def _read_ultralytics_data_yaml(self, dataset_root: Path) -> dict[str, object]:
        data_yaml = dataset_root / "data.yaml"
        if not data_yaml.exists() or not data_yaml.is_file():
            raise ValueError("W wybranym folderze nie znaleziono pliku data.yaml dla datasetu YOLO Pose.")

        names: dict[int, str] = {}
        config: dict[str, object] = {}
        in_names_block = False

        for raw_line in data_yaml.read_text(encoding="utf-8").splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if in_names_block and not raw_line[:1].isspace():
                in_names_block = False

            if in_names_block:
                match = re.match(r"\s*(\d+)\s*:\s*(.+?)\s*$", raw_line)
                if not match:
                    continue
                names[int(match.group(1))] = self._strip_yaml_scalar(match.group(2))
                continue

            if stripped.startswith("names:"):
                inline_value = stripped.partition(":")[2].strip()
                if inline_value:
                    parsed_names = self._parse_ultralytics_inline_names(inline_value)
                    if parsed_names:
                        names.update(parsed_names)
                in_names_block = True
                continue

            key, separator, value = stripped.partition(":")
            if not separator:
                continue
            config[key.strip()] = self._strip_yaml_scalar(value.strip())

        if not names:
            raise ValueError("Plik data.yaml nie zawiera mapowania klas 'names' dla YOLO Pose.")

        return {
            "names": names,
            "train": str(config.get("train") or "train.txt"),
            "val": str(config.get("val") or config.get("valid") or "valid.txt"),
            "test": str(config.get("test") or "test.txt"),
        }

    def _read_ultralytics_split_entries(self, dataset_root: Path, metadata: dict[str, object]) -> list[tuple[str, str]]:
        entries: list[tuple[str, str]] = []
        for split_name, metadata_key in (("train", "train"), ("valid", "val"), ("test", "test")):
            split_manifest = dataset_root / str(metadata.get(metadata_key) or "")
            if not split_manifest.exists() or not split_manifest.is_file():
                continue
            for raw_line in split_manifest.read_text(encoding="utf-8").splitlines():
                image_relative_path = raw_line.strip()
                if image_relative_path:
                    entries.append((split_name, image_relative_path))
        return entries

    def _resolve_ultralytics_label_path(self, dataset_root: Path, split_name: str, image_relative_path: str) -> Path:
        image_path = Path(image_relative_path)
        label_relative = image_path.with_suffix(".txt")
        image_parts = list(image_path.parts)
        if len(image_parts) >= 2 and image_parts[0] == "images":
            image_parts[0] = "labels"
            label_relative = Path(*image_parts).with_suffix(".txt")

        candidates = [
            dataset_root / label_relative,
            dataset_root / "labels" / split_name / f"{image_path.stem}.txt",
            dataset_root / "labels" / f"{image_path.stem}.txt",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return candidates[0]

    def _load_yolo_pose_annotations(
        self,
        label_path: Path,
        label_lookup: dict[str, LabelTemplate],
        class_names_by_index: dict[int, str],
    ) -> list[dict[str, object]]:
        annotations: list[dict[str, object]] = []
        for line_number, raw_line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped_line = raw_line.strip()
            if not stripped_line:
                continue
            parts = stripped_line.split()
            if len(parts) < 8:
                raise ValueError(f"Nieprawidlowy wpis YOLO Pose w {label_path.name}:{line_number}.")
            try:
                class_id = int(parts[0])
                numeric_values = [float(value) for value in parts[1:]]
            except ValueError as error:
                raise ValueError(f"Nieprawidlowe wartosci YOLO Pose w {label_path.name}:{line_number}.") from error

            if len(numeric_values) < 7 or (len(numeric_values) - 4) % 3 != 0:
                raise ValueError(f"Wpis YOLO Pose w {label_path.name}:{line_number} ma nieprawidlowa liczbe wartosci.")

            label_name = class_names_by_index.get(class_id)
            if not label_name:
                raise ValueError(f"Klasa {class_id} z {label_path.name}:{line_number} nie istnieje w data.yaml.")
            label = self._resolve_import_label(label_lookup, label_name)
            if label.label_type not in {"Skeleton", "Point"}:
                raise ValueError(
                    f"Import YOLO Pose nie moze uzyc etykiety '{label_name}' z {label_path.name}:{line_number}. "
                    + self._format_expected_received("Skeleton albo Point", label.label_type)
                )

            keypoint_values = numeric_values[4:]
            parsed_count = len(keypoint_values) // 3
            expected_count = self._get_expected_pose_keypoint_count(label, parsed_count)
            if expected_count < 1:
                raise ValueError(f"Nie udalo sie ustalic liczby keypointow dla etykiety '{label_name}'.")
            if parsed_count != expected_count:
                raise ValueError(
                    f"Nieprawidlowa liczba keypointow w {label_path.name}:{line_number} dla etykiety '{label_name}'. "
                    + self._format_expected_received(expected_count, parsed_count)
                )

            points: list[dict[str, object]] = []
            for index in range(parsed_count):
                value_offset = index * 3
                x_pos = float(keypoint_values[value_offset])
                y_pos = float(keypoint_values[value_offset + 1])
                visibility = 0 if int(round(keypoint_values[value_offset + 2])) <= 0 else 2
                point_payload: dict[str, object] = {
                    "x": round(x_pos, 6) if visibility > 0 else 0.0,
                    "y": round(y_pos, 6) if visibility > 0 else 0.0,
                }
                if visibility == 0:
                    point_payload["visibility"] = 0
                points.append(point_payload)

            annotation_definition: dict[str, object] = {"type": label.label_type, "points": points}
            if label.label_type == "Skeleton":
                annotation_definition["point_count"] = len(points)

            annotations.append(
                {
                    "label_template_id": label.id,
                    "annotation_definition": annotation_definition,
                    "note": "",
                }
            )
        return annotations

    def _get_expected_pose_keypoint_count(self, label: LabelTemplate, fallback_count: int) -> int:
        if label.label_type == "Point":
            return 1
        preview_definition = label.preview_definition if isinstance(label.preview_definition, dict) else None
        preview_points = preview_definition.get("points", []) if preview_definition else []
        if isinstance(preview_points, list) and preview_points:
            return len(preview_points)
        return fallback_count

    def _parse_ultralytics_inline_names(self, raw_value: str) -> dict[int, str]:
        stripped_value = raw_value.strip()
        if not stripped_value:
            return {}
        if stripped_value.startswith("[") and stripped_value.endswith("]"):
            inner_values = [self._strip_yaml_scalar(item.strip()) for item in stripped_value[1:-1].split(",") if item.strip()]
            return {index: value for index, value in enumerate(inner_values)}
        if stripped_value.startswith("{") and stripped_value.endswith("}"):
            mapping: dict[int, str] = {}
            entries = [item.strip() for item in stripped_value[1:-1].split(",") if item.strip()]
            for entry in entries:
                key, separator, value = entry.partition(":")
                if not separator:
                    continue
                try:
                    mapping[int(key.strip())] = self._strip_yaml_scalar(value.strip())
                except ValueError:
                    continue
            return mapping
        return {}

    def _strip_yaml_scalar(self, value: str) -> str:
        stripped = value.strip()
        if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
            return stripped[1:-1]
        return stripped

    def _resolve_import_image_path(
        self,
        dataset_root: Path,
        raw_path: object,
        file_name: object,
        split_name: object,
    ) -> Path:
        candidates: list[Path] = []
        if isinstance(raw_path, str) and raw_path.strip():
            raw_image_path = Path(raw_path)
            candidates.append(raw_image_path)
            candidates.append(dataset_root / raw_path)
        if isinstance(file_name, str) and file_name.strip():
            candidates.append(dataset_root / file_name)
            if isinstance(split_name, str) and split_name.strip():
                candidates.append(dataset_root / "images" / split_name / file_name)
                candidates.append(dataset_root / split_name / "images" / file_name)
            candidates.append(dataset_root / "images" / file_name)

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
        target_name = str(file_name or raw_path or "obrazu")
        raise ValueError(f"Nie znaleziono pliku obrazu dla wpisu '{target_name}' w datasecie.")

    def _build_import_definition_from_coco_annotation(
        self,
        annotation: dict[str, object],
        label: LabelTemplate,
        image_width: int,
        image_height: int,
        include_keypoints: bool,
    ) -> dict[str, object] | None:
        safe_width = max(image_width, 1)
        safe_height = max(image_height, 1)
        if label.label_type == "Bounding box":
            bbox = annotation.get("bbox")
            if not isinstance(bbox, list) or len(bbox) < 4:
                raise ValueError(f"Brakuje bbox dla etykiety '{label.name}'.")
            x_pos, y_pos, width, height = [float(value) for value in bbox[:4]]
            return {
                "type": "Bounding box",
                "points": [
                    {"x": round(x_pos / safe_width, 6), "y": round(y_pos / safe_height, 6)},
                    {"x": round((x_pos + width) / safe_width, 6), "y": round((y_pos + height) / safe_height, 6)},
                ],
            }

        if label.label_type in {"Polygon", "Segmentacja (maska)"}:
            segmentation = annotation.get("segmentation")
            if not isinstance(segmentation, list) or not segmentation:
                raise ValueError(f"Brakuje segmentacji dla etykiety '{label.name}'.")
            raw_points = segmentation[0] if isinstance(segmentation[0], list) else segmentation
            if not isinstance(raw_points, list) or len(raw_points) < 6:
                raise ValueError(f"Segmentacja dla etykiety '{label.name}' jest nieprawidlowa.")
            points = []
            for index in range(0, len(raw_points) - 1, 2):
                points.append(
                    {
                        "x": round(float(raw_points[index]) / safe_width, 6),
                        "y": round(float(raw_points[index + 1]) / safe_height, 6),
                    }
                )
            return {"type": label.label_type, "points": points}

        if label.label_type in {"Skeleton", "Point"}:
            if not include_keypoints:
                raise ValueError(
                    f"Format COCO bez keypointow nie zawiera danych dla etykiety '{label.name}'. "
                    + self._format_expected_received("annotacje z keypointami", "brak keypointow")
                )
            raw_keypoints = annotation.get("keypoints")
            if not isinstance(raw_keypoints, list) or len(raw_keypoints) < 3:
                received_count = len(raw_keypoints) // 3 if isinstance(raw_keypoints, list) else 0
                raise ValueError(
                    f"Brakuje keypointow dla etykiety '{label.name}'. "
                    + self._format_expected_received("co najmniej 1 keypoint", received_count)
                )
            points = []
            for index in range(0, len(raw_keypoints) - 2, 3):
                x_pos = float(raw_keypoints[index])
                y_pos = float(raw_keypoints[index + 1])
                visibility = 0 if int(raw_keypoints[index + 2]) <= 0 else 2
                point_payload = {
                    "x": round(x_pos / safe_width, 6) if visibility > 0 else 0.0,
                    "y": round(y_pos / safe_height, 6) if visibility > 0 else 0.0,
                }
                if visibility == 0:
                    point_payload["visibility"] = 0
                points.append(point_payload)
            payload: dict[str, object] = {"type": label.label_type, "points": points}
            if label.label_type == "Skeleton" and label.preview_definition is not None:
                preview_points = label.preview_definition.get("points", [])
                if isinstance(preview_points, list):
                    payload["point_count"] = len(preview_points)
            return payload

        if label.label_type == "Klasyfikacja":
            return None

        raise ValueError(f"Import COCO nie obsluguje typu etykiety '{label.label_type}'.")

    def _validate_annotation_definition(
        self,
        label: LabelTemplate,
        annotation_definition: dict[str, object] | None,
    ) -> None:
        if label.label_type == "Klasyfikacja":
            return

        template_definition = label.preview_definition
        if template_definition is None:
            return
        if annotation_definition is None:
            raise ValueError(
                f"Brakuje geometrii dla etykiety '{label.name}'. "
                + self._format_expected_received(f"geometria typu {label.label_type}", "brak")
            )

        template_points = template_definition.get("points", [])
        annotation_points = annotation_definition.get("points", [])
        if not isinstance(template_points, list):
            raise ValueError(f"Szablon etykiety '{label.name}' ma nieprawidlowy format punktow.")
        if not isinstance(annotation_points, list):
            raise ValueError(
                f"Nieprawidlowy format geometrii annotacji dla etykiety '{label.name}'. "
                + self._format_expected_received("lista punktow", type(annotation_points).__name__)
            )
        if annotation_definition.get("type") != label.label_type:
            raise ValueError(
                f"Typ geometrii annotacji nie zgadza sie z typem etykiety '{label.name}'. "
                + self._format_expected_received(label.label_type, annotation_definition.get("type") or "brak")
            )

        expected_count = len(template_points)
        received_count = len(annotation_points)
        if label.label_type == "Point" and received_count != 1:
            raise ValueError(
                f"Nieprawidlowa liczba punktow dla etykiety '{label.name}'. "
                + self._format_expected_received(1, received_count)
            )
        if label.label_type == "Bounding box" and received_count != 2:
            raise ValueError(
                f"Nieprawidlowa liczba punktow dla etykiety '{label.name}'. "
                + self._format_expected_received(2, received_count)
            )
        if label.label_type == "Skeleton" and received_count != expected_count:
            raise ValueError(
                f"Nieprawidlowa liczba keypointow dla etykiety '{label.name}'. "
                + self._format_expected_received(expected_count, received_count)
            )
        if label.label_type == "Polyline" and received_count < max(2, expected_count):
            raise ValueError(
                f"Nieprawidlowa liczba punktow dla etykiety '{label.name}'. "
                + self._format_expected_received(f"co najmniej {max(2, expected_count)}", received_count)
            )
        if label.label_type in {"Polygon", "Segmentacja (maska)"} and received_count < max(3, expected_count):
            raise ValueError(
                f"Nieprawidlowa liczba punktow dla etykiety '{label.name}'. "
                + self._format_expected_received(f"co najmniej {max(3, expected_count)}", received_count)
            )

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

    def _export_coco_like_json(self, export_root: Path, manifest: dict, include_images: bool) -> None:
        prepared_manifest = self._build_generic_manifest(export_root, manifest, include_images)
        categories: list[dict[str, object]] = []
        category_by_id: dict[int, int] = {}
        category_by_name: dict[str, int] = {}
        next_category_id = 1

        for label in prepared_manifest["labels"]:
            raw_label_id = label.get("id")
            category_id = raw_label_id if isinstance(raw_label_id, int) else next_category_id
            next_category_id = max(next_category_id, category_id + 1)
            categories.append(
                {
                    "id": category_id,
                    "name": label["name"],
                    "supercategory": label["label_type"],
                    "label_type": label["label_type"],
                }
            )
            if isinstance(raw_label_id, int):
                category_by_id[raw_label_id] = category_id
            category_by_name[label["name"]] = category_id

        images: list[dict[str, object]] = []
        annotations: list[dict[str, object]] = []
        annotation_id = 1

        for image_id, item in enumerate(prepared_manifest["items"], start=1):
            images.append(
                {
                    "id": image_id,
                    "file_name": item["image_name"],
                    "path": item["image_path"],
                    "split": item["split"],
                    "task": item["task"],
                }
            )
            for annotation in item["annotations"]:
                category_id = None
                raw_template_id = annotation.get("label_template_id")
                if isinstance(raw_template_id, int):
                    category_id = category_by_id.get(raw_template_id)
                if category_id is None:
                    category_id = category_by_name.get(annotation["label_name"], 0)

                annotations.append(
                    {
                        "id": annotation_id,
                        "image_id": image_id,
                        "category_id": category_id,
                        "label_name": annotation["label_name"],
                        "label_type": annotation["label_type"],
                        "source": annotation["source"],
                        "is_visible": annotation["is_visible"],
                        "note": annotation["note"],
                        **self._build_coco_like_geometry(annotation.get("annotation_definition")),
                    }
                )
                annotation_id += 1

        payload = {
            "info": prepared_manifest["project"],
            "images": images,
            "categories": categories,
            "annotations": annotations,
        }
        (export_root / "annotations_coco.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _export_csv(self, export_root: Path, manifest: dict, include_images: bool) -> None:
        prepared_manifest = self._build_generic_manifest(export_root, manifest, include_images)
        with (export_root / "annotations.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "split",
                    "task",
                    "image_name",
                    "label_name",
                    "label_type",
                    "source",
                    "visible",
                    "note",
                    "geometry_json",
                ]
            )
            for item in prepared_manifest["items"]:
                if not item["annotations"]:
                    writer.writerow([item["split"], item["task"], item["image_name"], "", "", "", "", "", ""])
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
                            json.dumps(annotation.get("annotation_definition"), ensure_ascii=False),
                        ]
                    )

    def _export_yolo(self, export_root: Path, manifest: dict, include_images: bool) -> None:
        labels = manifest["labels"]
        _label_id_to_index, label_name_to_index = self._build_label_index_maps(labels)
        subset_files: dict[str, list[str]] = {"train": [], "valid": []}

        for item in manifest["items"]:
            subset = "train" if item["split"] == "train" else "valid"
            subset_dir = export_root / f"obj_{subset}_data"
            subset_dir.mkdir(parents=True, exist_ok=True)
            self._copy_image_if_requested(item["source_image_path"], subset_dir / item["image_name"], include_images)

            lines: list[str] = []
            for annotation in item["annotations"]:
                if annotation["label_type"] != "Bounding box":
                    continue
                bbox = self._bbox_from_annotation_definition(annotation.get("annotation_definition"))
                if bbox is None:
                    continue
                class_id = label_name_to_index.get(annotation["label_name"])
                if class_id is None:
                    continue
                center_x, center_y, width, height = self._bbox_to_yolo(bbox)
                lines.append(f"{class_id} {center_x:.6f} {center_y:.6f} {width:.6f} {height:.6f}")

            (subset_dir / f"{Path(item['image_name']).stem}.txt").write_text("\n".join(lines), encoding="utf-8")
            subset_files[subset].append(f"obj_{subset}_data/{item['image_name']}")

        (export_root / "obj.names").write_text("\n".join(label["name"] for label in labels), encoding="utf-8")
        (export_root / "obj.data").write_text(
            "\n".join(
                [
                    f"classes = {len(labels)}",
                    "names = obj.names",
                    "train = train.txt",
                    "valid = valid.txt",
                    "backup = backup/",
                ]
            ),
            encoding="utf-8",
        )
        (export_root / "train.txt").write_text("\n".join(subset_files["train"]), encoding="utf-8")
        (export_root / "valid.txt").write_text("\n".join(subset_files["valid"]), encoding="utf-8")

    def _export_ultralytics_yolo_detection(self, export_root: Path, manifest: dict, include_images: bool) -> None:
        self._export_ultralytics_dataset(export_root, manifest, include_images, mode="detection")

    def _export_ultralytics_yolo_segmentation(self, export_root: Path, manifest: dict, include_images: bool) -> None:
        self._export_ultralytics_dataset(export_root, manifest, include_images, mode="segmentation")

    def _export_yolo_pose(self, export_root: Path, manifest: dict, include_images: bool) -> None:
        self._export_ultralytics_dataset(export_root, manifest, include_images, mode="pose")

    def _export_ultralytics_dataset(self, export_root: Path, manifest: dict, include_images: bool, mode: str) -> None:
        labels = manifest["labels"]
        _label_id_to_index, label_name_to_index = self._build_label_index_maps(labels)
        keypoint_counts = self._collect_keypoint_label_counts(manifest)
        max_keypoint_count = max(keypoint_counts.values(), default=0)
        split_files: dict[str, list[str]] = {"train": [], "valid": [], "test": []}

        for split_name in split_files:
            (export_root / "labels" / split_name).mkdir(parents=True, exist_ok=True)
            if include_images:
                (export_root / "images" / split_name).mkdir(parents=True, exist_ok=True)

        for item in manifest["items"]:
            split_name = item["split"]
            image_target = export_root / "images" / split_name / item["image_name"]
            self._copy_image_if_requested(item["source_image_path"], image_target, include_images)

            lines: list[str] = []
            for annotation in item["annotations"]:
                class_id = label_name_to_index.get(annotation["label_name"])
                if class_id is None:
                    continue

                if mode == "detection":
                    if annotation["label_type"] != "Bounding box":
                        continue
                    bbox = self._bbox_from_annotation_definition(annotation.get("annotation_definition"))
                    if bbox is None:
                        continue
                    center_x, center_y, width, height = self._bbox_to_yolo(bbox)
                    lines.append(f"{class_id} {center_x:.6f} {center_y:.6f} {width:.6f} {height:.6f}")
                    continue

                if mode == "segmentation":
                    if annotation["label_type"] not in {"Polygon", "Segmentacja (maska)"}:
                        continue
                    points = self._segmentation_points_from_annotation_definition(annotation.get("annotation_definition"))
                    if len(points) < 3:
                        continue
                    point_values = " ".join(f"{x_pos:.6f} {y_pos:.6f}" for x_pos, y_pos in points)
                    lines.append(f"{class_id} {point_values}")
                    continue

                if mode == "pose":
                    if annotation["label_type"] not in {"Skeleton", "Point"}:
                        continue
                    keypoint_entries = self._keypoint_entries_from_annotation_definition(annotation.get("annotation_definition"))
                    if not keypoint_entries:
                        continue
                    visible_points = [(x_pos, y_pos) for x_pos, y_pos, visibility in keypoint_entries if visibility > 0]
                    bbox = self._bbox_from_points(visible_points or [(x_pos, y_pos) for x_pos, y_pos, _visibility in keypoint_entries])
                    if bbox is None:
                        continue
                    center_x, center_y, width, height = self._bbox_to_yolo(bbox)
                    expected_count = keypoint_counts.get(annotation["label_name"], len(keypoint_entries))
                    padded_points = list(keypoint_entries[:expected_count])
                    while len(padded_points) < max_keypoint_count:
                        padded_points.append((0.0, 0.0, 0))
                    keypoint_values: list[str] = []
                    for x_pos, y_pos, visibility in padded_points:
                        export_x = x_pos if visibility > 0 else 0.0
                        export_y = y_pos if visibility > 0 else 0.0
                        keypoint_values.extend([f"{x_pos:.6f}", f"{y_pos:.6f}", str(visibility)])
                        keypoint_values[-3] = f"{export_x:.6f}"
                        keypoint_values[-2] = f"{export_y:.6f}"
                    lines.append(
                        " ".join(
                            [
                                str(class_id),
                                f"{center_x:.6f}",
                                f"{center_y:.6f}",
                                f"{width:.6f}",
                                f"{height:.6f}",
                                *keypoint_values,
                            ]
                        )
                    )

            label_path = export_root / "labels" / split_name / f"{Path(item['image_name']).stem}.txt"
            label_path.write_text("\n".join(lines), encoding="utf-8")
            split_files[split_name].append(f"images/{split_name}/{item['image_name']}")

        self._write_ultralytics_metadata(export_root, labels, split_files, max_keypoint_count if mode == "pose" else None)

    def _export_coco(self, export_root: Path, manifest: dict, include_images: bool) -> None:
        annotations_dir = export_root / "annotations"
        annotations_dir.mkdir(parents=True, exist_ok=True)
        categories, category_by_name = self._build_coco_categories(manifest["labels"])

        for split_name, items in self._group_items_by_split(manifest).items():
            images: list[dict[str, object]] = []
            annotations: list[dict[str, object]] = []
            image_id_map: dict[int, int] = {}
            annotation_id = 1

            if include_images:
                (export_root / "images" / split_name).mkdir(parents=True, exist_ok=True)

            for image_index, item in enumerate(items, start=1):
                image_id_map[item["image_id"]] = image_index
                self._copy_image_if_requested(
                    item["source_image_path"],
                    export_root / "images" / split_name / item["image_name"],
                    include_images,
                )
                images.append(
                    {
                        "id": image_index,
                        "file_name": item["image_name"],
                        "width": item["width"],
                        "height": item["height"],
                    }
                )

                for annotation in item["annotations"]:
                    geometry = self._build_coco_instance_geometry(
                        annotation.get("annotation_definition"),
                        item["width"],
                        item["height"],
                    )
                    if geometry is None:
                        continue
                    annotations.append(
                        {
                            "id": annotation_id,
                            "image_id": image_index,
                            "category_id": category_by_name[annotation["label_name"]],
                            "bbox": geometry["bbox"],
                            "area": geometry["area"],
                            "segmentation": geometry["segmentation"],
                            "iscrowd": 0,
                            "attributes": {
                                "source": annotation["source"],
                                "visible": annotation["is_visible"],
                                "note": annotation["note"],
                            },
                        }
                    )
                    annotation_id += 1

            payload = {
                "info": manifest["project"],
                "licenses": [],
                "images": images,
                "annotations": annotations,
                "categories": categories,
            }
            (annotations_dir / f"instances_{split_name}.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def _export_coco_keypoints(self, export_root: Path, manifest: dict, include_images: bool) -> None:
        annotations_dir = export_root / "annotations"
        annotations_dir.mkdir(parents=True, exist_ok=True)
        keypoint_counts = self._collect_keypoint_label_counts(manifest)
        categories, category_by_name = self._build_coco_categories(manifest["labels"], keypoint_counts=keypoint_counts)

        for split_name, items in self._group_items_by_split(manifest).items():
            images: list[dict[str, object]] = []
            annotations: list[dict[str, object]] = []
            annotation_id = 1

            if include_images:
                (export_root / "images" / split_name).mkdir(parents=True, exist_ok=True)

            for image_index, item in enumerate(items, start=1):
                self._copy_image_if_requested(
                    item["source_image_path"],
                    export_root / "images" / split_name / item["image_name"],
                    include_images,
                )
                images.append(
                    {
                        "id": image_index,
                        "file_name": item["image_name"],
                        "width": item["width"],
                        "height": item["height"],
                    }
                )

                for annotation in item["annotations"]:
                    if annotation["label_type"] not in {"Skeleton", "Point"}:
                        continue
                    keypoint_count = keypoint_counts.get(annotation["label_name"], 0)
                    geometry = self._build_coco_keypoints_geometry(
                        annotation.get("annotation_definition"),
                        item["width"],
                        item["height"],
                        keypoint_count,
                    )
                    if geometry is None:
                        continue
                    annotations.append(
                        {
                            "id": annotation_id,
                            "image_id": image_index,
                            "category_id": category_by_name[annotation["label_name"]],
                            "bbox": geometry["bbox"],
                            "area": geometry["area"],
                            "segmentation": [],
                            "iscrowd": 0,
                            "keypoints": geometry["keypoints"],
                            "num_keypoints": geometry["num_keypoints"],
                            "attributes": {
                                "source": annotation["source"],
                                "visible": annotation["is_visible"],
                                "note": annotation["note"],
                            },
                        }
                    )
                    annotation_id += 1

            payload = {
                "info": manifest["project"],
                "licenses": [],
                "images": images,
                "annotations": annotations,
                "categories": categories,
            }
            (annotations_dir / f"person_keypoints_{split_name}.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def _export_pascal_voc(self, export_root: Path, manifest: dict, include_images: bool) -> None:
        jpeg_dir = export_root / "JPEGImages"
        annotations_dir = export_root / "Annotations"
        image_sets_dir = export_root / "ImageSets" / "Main"
        annotations_dir.mkdir(parents=True, exist_ok=True)
        image_sets_dir.mkdir(parents=True, exist_ok=True)
        if include_images:
            jpeg_dir.mkdir(parents=True, exist_ok=True)

        split_names: dict[str, list[str]] = {"train": [], "valid": [], "test": []}
        all_names: list[str] = []

        for item in manifest["items"]:
            base_name = Path(item["image_name"]).stem
            all_names.append(base_name)
            split_names[item["split"]].append(base_name)
            self._copy_image_if_requested(item["source_image_path"], jpeg_dir / item["image_name"], include_images)

            root = ET.Element("annotation")
            ET.SubElement(root, "folder").text = "JPEGImages"
            ET.SubElement(root, "filename").text = item["image_name"]
            ET.SubElement(root, "path").text = str((jpeg_dir / item["image_name"]).as_posix())
            source = ET.SubElement(root, "source")
            ET.SubElement(source, "database").text = manifest["project"]["name"]
            size = ET.SubElement(root, "size")
            ET.SubElement(size, "width").text = str(item["width"])
            ET.SubElement(size, "height").text = str(item["height"])
            ET.SubElement(size, "depth").text = "3"
            ET.SubElement(root, "segmented").text = "0"

            for annotation in item["annotations"]:
                if annotation["label_type"] != "Bounding box":
                    continue
                bbox = self._bbox_from_annotation_definition(annotation.get("annotation_definition"))
                if bbox is None:
                    continue
                x_min, y_min, x_max, y_max = self._normalized_bbox_to_absolute(bbox, item["width"], item["height"], ensure_positive=True)
                obj = ET.SubElement(root, "object")
                ET.SubElement(obj, "name").text = annotation["label_name"]
                ET.SubElement(obj, "pose").text = "Unspecified"
                ET.SubElement(obj, "truncated").text = "0"
                ET.SubElement(obj, "difficult").text = "0"
                ET.SubElement(obj, "occluded").text = "0"
                bndbox = ET.SubElement(obj, "bndbox")
                ET.SubElement(bndbox, "xmin").text = str(int(round(x_min)))
                ET.SubElement(bndbox, "ymin").text = str(int(round(y_min)))
                ET.SubElement(bndbox, "xmax").text = str(int(round(x_max)))
                ET.SubElement(bndbox, "ymax").text = str(int(round(y_max)))

            tree = ET.ElementTree(root)
            ET.indent(tree, space="  ")
            tree.write(annotations_dir / f"{base_name}.xml", encoding="utf-8", xml_declaration=True)

        (export_root / "labelmap.txt").write_text(
            "\n".join(["background:::", *[f"{label['name']}:::" for label in manifest["labels"]]]),
            encoding="utf-8",
        )
        (image_sets_dir / "default.txt").write_text("\n".join(all_names), encoding="utf-8")
        for split_name, names in split_names.items():
            (image_sets_dir / f"{split_name}.txt").write_text("\n".join(names), encoding="utf-8")

    def _export_imagenet(self, export_root: Path, manifest: dict, include_images: bool) -> None:
        _label_id_to_index, label_name_to_index = self._build_label_index_maps(manifest["labels"])
        split_lines: dict[str, list[str]] = {"train": [], "valid": [], "test": []}

        for item in manifest["items"]:
            class_names = sorted({annotation["label_name"] for annotation in item["annotations"] if annotation["label_type"] == "Klasyfikacja"})
            if len(class_names) != 1:
                raise ValueError(f"ImageNet wymaga dokladnie jednej etykiety klasyfikacyjnej na obraz: {item['image_name']}")

            class_name = class_names[0]
            class_index = label_name_to_index[class_name]
            relative_path = item["image_name"]
            if include_images:
                target_dir = export_root / self._slugify(class_name)
                target_dir.mkdir(parents=True, exist_ok=True)
                target_path = target_dir / item["image_name"]
                self._copy_image_if_requested(item["source_image_path"], target_path, include_images)
                relative_path = f"{self._slugify(class_name)}/{item['image_name']}"

            split_lines[item["split"]].append(f"{relative_path} {class_index}")

        (export_root / "synsets.txt").write_text(
            "\n".join(label["name"] for label in manifest["labels"]),
            encoding="utf-8",
        )
        for split_name, lines in split_lines.items():
            (export_root / f"{split_name}.txt").write_text("\n".join(lines), encoding="utf-8")

    def _build_generic_manifest(self, export_root: Path, manifest: dict, include_images: bool) -> dict:
        prepared_manifest = {
            "project": dict(manifest["project"]),
            "labels": list(manifest["labels"]),
            "items": [],
        }
        for item in manifest["items"]:
            export_item = dict(item)
            if include_images:
                image_path = export_root / item["split"] / "images" / item["image_name"]
                self._copy_image_if_requested(item["source_image_path"], image_path, include_images)
                export_item["image_path"] = str(image_path)
            else:
                export_item["image_path"] = item["source_image_path"]
            prepared_manifest["items"].append(export_item)
        return prepared_manifest

    def _copy_image_if_requested(self, source_image_path: str, target_path: Path, include_images: bool) -> None:
        if not include_images:
            return
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_image_path, target_path)

    def _get_image_size(self, image_path: str) -> tuple[int, int]:
        if PILImage is None:
            raise ValueError("Eksport wymaga zainstalowanego Pillow do odczytu rozmiarow obrazow.")
        with PILImage.open(image_path) as image:
            return image.size

    def _build_label_index_maps(self, labels: list[dict]) -> tuple[dict[int, int], dict[str, int]]:
        label_id_to_index: dict[int, int] = {}
        label_name_to_index: dict[str, int] = {}
        for index, label in enumerate(labels):
            raw_label_id = label.get("id")
            if isinstance(raw_label_id, int):
                label_id_to_index[raw_label_id] = index
            label_name_to_index[label["name"]] = index
        return label_id_to_index, label_name_to_index

    def _group_items_by_split(self, manifest: dict) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {"train": [], "valid": [], "test": []}
        for item in manifest["items"]:
            grouped.setdefault(item["split"], []).append(item)
        return grouped

    def _normalized_points(self, annotation_definition: dict[str, object] | None) -> list[tuple[float, float]]:
        if not isinstance(annotation_definition, dict):
            return []
        points = annotation_definition.get("points", [])
        if not isinstance(points, list):
            return []
        normalized_points: list[tuple[float, float]] = []
        for point in points:
            if not isinstance(point, dict) or "x" not in point or "y" not in point:
                continue
            normalized_points.append((float(point["x"]), float(point["y"])))
        return normalized_points

    def _bbox_from_annotation_definition(self, annotation_definition: dict[str, object] | None) -> tuple[float, float, float, float] | None:
        if not isinstance(annotation_definition, dict):
            return None
        if annotation_definition.get("type") != "Bounding box":
            return None
        points = self._normalized_points(annotation_definition)
        if len(points) < 2:
            return None
        return self._bbox_from_points(points[:2])

    def _segmentation_points_from_annotation_definition(self, annotation_definition: dict[str, object] | None) -> list[tuple[float, float]]:
        if not isinstance(annotation_definition, dict):
            return []
        if annotation_definition.get("type") not in {"Polygon", "Segmentacja (maska)"}:
            return []
        return self._normalized_points(annotation_definition)

    def _keypoint_entries_from_annotation_definition(self, annotation_definition: dict[str, object] | None) -> list[tuple[float, float, int]]:
        if not isinstance(annotation_definition, dict):
            return []
        if annotation_definition.get("type") not in {"Skeleton", "Point"}:
            return []
        points = annotation_definition.get("points", [])
        if not isinstance(points, list):
            return []

        keypoint_entries: list[tuple[float, float, int]] = []
        for point in points:
            if not isinstance(point, dict) or "x" not in point or "y" not in point:
                continue
            raw_visibility = point.get("visibility", 2)
            try:
                visibility = 0 if int(raw_visibility) <= 0 else 2
            except (TypeError, ValueError):
                visibility = 2
            keypoint_entries.append((float(point["x"]), float(point["y"]), visibility))
        return keypoint_entries

    def _keypoints_from_annotation_definition(self, annotation_definition: dict[str, object] | None) -> list[tuple[float, float]]:
        return [
            (x_pos, y_pos)
            for x_pos, y_pos, visibility in self._keypoint_entries_from_annotation_definition(annotation_definition)
            if visibility > 0
        ]

    def _bbox_from_points(self, points: list[tuple[float, float]]) -> tuple[float, float, float, float] | None:
        if not points:
            return None
        x_values = [point[0] for point in points]
        y_values = [point[1] for point in points]
        x_min = min(x_values)
        y_min = min(y_values)
        x_max = max(x_values)
        y_max = max(y_values)
        if x_max == x_min:
            x_max = min(1.0, x_max + 1e-6)
        if y_max == y_min:
            y_max = min(1.0, y_max + 1e-6)
        return (x_min, y_min, x_max, y_max)

    def _bbox_to_yolo(self, bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        x_min, y_min, x_max, y_max = bbox
        width = max(x_max - x_min, 1e-6)
        height = max(y_max - y_min, 1e-6)
        center_x = x_min + width / 2
        center_y = y_min + height / 2
        return center_x, center_y, width, height

    def _normalized_bbox_to_absolute(
        self,
        bbox: tuple[float, float, float, float],
        image_width: int,
        image_height: int,
        ensure_positive: bool = False,
    ) -> tuple[float, float, float, float]:
        x_min, y_min, x_max, y_max = bbox
        abs_x_min = max(0.0, x_min * image_width)
        abs_y_min = max(0.0, y_min * image_height)
        abs_x_max = min(float(image_width), x_max * image_width)
        abs_y_max = min(float(image_height), y_max * image_height)
        if ensure_positive:
            if abs_x_max <= abs_x_min:
                abs_x_max = min(float(image_width), abs_x_min + 1.0)
            if abs_y_max <= abs_y_min:
                abs_y_max = min(float(image_height), abs_y_min + 1.0)
        return abs_x_min, abs_y_min, abs_x_max, abs_y_max

    def _collect_keypoint_label_counts(self, manifest: dict) -> dict[str, int]:
        counts: dict[str, int] = {}
        for label in manifest["labels"]:
            if label["label_type"] == "Point":
                counts[label["name"]] = 1
                continue
            if label["label_type"] != "Skeleton":
                continue
            preview_definition = label.get("preview_definition")
            preview_points = self._normalized_points(preview_definition if isinstance(preview_definition, dict) else None)
            counts[label["name"]] = len(preview_points)

        for item in manifest["items"]:
            for annotation in item["annotations"]:
                if annotation["label_type"] not in {"Skeleton", "Point"}:
                    continue
                counts[annotation["label_name"]] = max(
                    counts.get(annotation["label_name"], 0),
                    len(self._normalized_points(annotation.get("annotation_definition"))),
                )
        return counts

    def _build_coco_categories(
        self,
        labels: list[dict],
        keypoint_counts: dict[str, int] | None = None,
    ) -> tuple[list[dict[str, object]], dict[str, int]]:
        categories: list[dict[str, object]] = []
        category_by_name: dict[str, int] = {}
        for index, label in enumerate(labels, start=1):
            category_id = int(label["id"]) if isinstance(label.get("id"), int) else index
            category = {
                "id": category_id,
                "name": label["name"],
                "supercategory": label["label_type"],
            }
            if keypoint_counts is not None:
                keypoint_count = keypoint_counts.get(label["name"], 0)
                category["keypoints"] = [f"p{point_index}" for point_index in range(1, keypoint_count + 1)]
                category["skeleton"] = []
            categories.append(category)
            category_by_name[label["name"]] = category_id
        return categories, category_by_name

    def _build_coco_instance_geometry(
        self,
        annotation_definition: dict[str, object] | None,
        image_width: int,
        image_height: int,
    ) -> dict[str, object] | None:
        if not isinstance(annotation_definition, dict):
            return None

        annotation_type = annotation_definition.get("type")
        if annotation_type == "Bounding box":
            bbox = self._bbox_from_annotation_definition(annotation_definition)
            if bbox is None:
                return None
            x_min, y_min, x_max, y_max = self._normalized_bbox_to_absolute(bbox, image_width, image_height, ensure_positive=True)
            width = x_max - x_min
            height = y_max - y_min
            return {
                "bbox": [round(x_min, 2), round(y_min, 2), round(width, 2), round(height, 2)],
                "area": round(width * height, 2),
                "segmentation": [],
            }

        if annotation_type in {"Polygon", "Segmentacja (maska)"}:
            points = self._segmentation_points_from_annotation_definition(annotation_definition)
            if len(points) < 3:
                return None
            absolute_points = [(x_pos * image_width, y_pos * image_height) for x_pos, y_pos in points]
            bbox = self._bbox_from_points(points)
            if bbox is None:
                return None
            x_min, y_min, x_max, y_max = self._normalized_bbox_to_absolute(bbox, image_width, image_height, ensure_positive=True)
            return {
                "bbox": [round(x_min, 2), round(y_min, 2), round(x_max - x_min, 2), round(y_max - y_min, 2)],
                "area": round(self._polygon_area(absolute_points), 2),
                "segmentation": [[round(value, 2) for point in absolute_points for value in point]],
            }

        return None

    def _build_coco_keypoints_geometry(
        self,
        annotation_definition: dict[str, object] | None,
        image_width: int,
        image_height: int,
        keypoint_count: int,
    ) -> dict[str, object] | None:
        keypoint_entries = self._keypoint_entries_from_annotation_definition(annotation_definition)
        if not keypoint_entries:
            return None
        visible_points = [(x_pos, y_pos) for x_pos, y_pos, visibility in keypoint_entries if visibility > 0]
        bbox = self._bbox_from_points(visible_points or [(x_pos, y_pos) for x_pos, y_pos, _visibility in keypoint_entries])
        if bbox is None:
            return None
        x_min, y_min, x_max, y_max = self._normalized_bbox_to_absolute(bbox, image_width, image_height, ensure_positive=True)
        padded_points = list(keypoint_entries[:keypoint_count])
        while len(padded_points) < keypoint_count:
            padded_points.append((0.0, 0.0, 0))

        keypoints: list[float] = []
        visible_count = 0
        for x_pos, y_pos, visibility in padded_points:
            if visibility > 0:
                keypoints.extend([round(x_pos * image_width, 2), round(y_pos * image_height, 2), visibility])
                visible_count += 1
            else:
                keypoints.extend([0.0, 0.0, 0])

        return {
            "bbox": [round(x_min, 2), round(y_min, 2), round(x_max - x_min, 2), round(y_max - y_min, 2)],
            "area": round((x_max - x_min) * (y_max - y_min), 2),
            "keypoints": keypoints,
            "num_keypoints": visible_count,
        }

    def _write_ultralytics_metadata(
        self,
        export_root: Path,
        labels: list[dict],
        split_files: dict[str, list[str]],
        keypoint_count: int | None,
    ) -> None:
        for split_name, files in split_files.items():
            (export_root / f"{split_name}.txt").write_text("\n".join(files), encoding="utf-8")

        yaml_lines = [
            "path: ./",
            "train: train.txt",
            "val: valid.txt",
            "test: test.txt",
        ]
        if keypoint_count is not None:
            yaml_lines.append(f"kpt_shape: [{keypoint_count}, 3]")
        yaml_lines.append("names:")
        for index, label in enumerate(labels):
            yaml_lines.append(f"  {index}: {label['name']}")
        (export_root / "data.yaml").write_text("\n".join(yaml_lines), encoding="utf-8")

    def _polygon_area(self, points: list[tuple[float, float]]) -> float:
        if len(points) < 3:
            return 0.0
        area = 0.0
        for index, (x_pos, y_pos) in enumerate(points):
            next_x, next_y = points[(index + 1) % len(points)]
            area += x_pos * next_y - next_x * y_pos
        return abs(area) / 2

    def _build_coco_like_geometry(self, annotation_definition: dict[str, object] | None) -> dict[str, object]:
        payload: dict[str, object] = {
            "bbox": None,
            "segmentation": [],
            "keypoints": [],
            "num_keypoints": 0,
            "raw_definition": annotation_definition,
        }
        if not isinstance(annotation_definition, dict):
            return payload

        label_type = annotation_definition.get("type")
        points = annotation_definition.get("points", [])
        if not isinstance(points, list):
            return payload

        normalized_points = [point for point in points if isinstance(point, dict) and "x" in point and "y" in point]
        if not normalized_points:
            return payload

        if label_type == "Bounding box" and len(normalized_points) >= 2:
            x_values = [point["x"] for point in normalized_points[:2]]
            y_values = [point["y"] for point in normalized_points[:2]]
            x_min = min(x_values)
            y_min = min(y_values)
            width = max(x_values) - x_min
            height = max(y_values) - y_min
            payload["bbox"] = [round(x_min, 6), round(y_min, 6), round(width, 6), round(height, 6)]
            payload["area"] = round(width * height, 6)
            return payload

        if label_type in {"Polygon", "Segmentacja (maska)"} and len(normalized_points) >= 3:
            payload["segmentation"] = [
                [round(value, 6) for point in normalized_points for value in (point["x"], point["y"])]
            ]
            return payload

        if label_type == "Polyline" and len(normalized_points) >= 2:
            payload["polyline"] = [round(value, 6) for point in normalized_points for value in (point["x"], point["y"])]
            return payload

        if label_type == "Skeleton":
            keypoint_entries = self._keypoint_entries_from_annotation_definition(annotation_definition)
            payload["keypoints"] = [
                round(value, 6)
                for x_pos, y_pos, visibility in keypoint_entries
                for value in (x_pos, y_pos, visibility)
            ]
            payload["num_keypoints"] = sum(1 for _x_pos, _y_pos, visibility in keypoint_entries if visibility > 0)
            return payload

        if label_type == "Point":
            keypoint_entries = self._keypoint_entries_from_annotation_definition(annotation_definition)
            if not keypoint_entries:
                return payload
            x_pos, y_pos, visibility = keypoint_entries[0]
            payload["keypoints"] = [round(x_pos, 6), round(y_pos, 6), visibility]
            payload["num_keypoints"] = 1 if visibility > 0 else 0
        return payload

    def _resolve_projects_root(self, storage_folder: str | None) -> Path:
        base_folder = Path(storage_folder).expanduser() if storage_folder and storage_folder.strip() else self.projects_root
        base_folder.mkdir(parents=True, exist_ok=True)
        return base_folder

    def _build_project_storage_path(self, base_folder: Path, project_name: str) -> Path:
        slug = self._slugify(project_name)
        candidate = base_folder / slug
        suffix = 2
        while candidate.exists():
            candidate = base_folder / f"{slug}_{suffix}"
            suffix += 1
        return candidate

    def _build_task_frames_path(self, project_folder: Path, task_name: str, source_name: str) -> Path:
        imports_root = project_folder / "task_imports"
        imports_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = self._slugify(f"{task_name}_{source_name}_{timestamp}")
        candidate = imports_root / slug
        suffix = 2
        while candidate.exists():
            candidate = imports_root / f"{slug}_{suffix}"
            suffix += 1
        return candidate

    def _store_label_preview(
        self,
        project_folder: Path,
        preview_image_path: str | None,
        index: int,
        label_name: str,
    ) -> str | None:
        if not preview_image_path:
            return None

        source_path = Path(preview_image_path)
        if not source_path.exists() or not source_path.is_file():
            raise ValueError(f"Nie znaleziono pliku podgladowego: {preview_image_path}")

        previews_folder = project_folder / "label_examples"
        previews_folder.mkdir(parents=True, exist_ok=True)
        target_name = f"{index:02d}_{self._slugify(label_name)}{source_path.suffix.lower()}"
        target_path = previews_folder / target_name
        shutil.copy2(source_path, target_path)
        return str(target_path)

    def _write_project_manifest(
        self,
        project_folder: Path,
        project_id: int,
        name: str,
        project_type: str,
        labels: list[LabelTemplate],
    ) -> None:
        payload = {
            "id": project_id,
            "name": name,
            "project_type": project_type,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "labels": [
                {
                    "name": label.name,
                    "label_type": label.label_type,
                    "preview_image_path": label.preview_image_path,
                    "preview_definition": label.preview_definition,
                }
                for label in labels
            ],
        }
        (project_folder / "project.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_").lower()
        return slug or "projekt"
