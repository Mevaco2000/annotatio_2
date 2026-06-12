from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AppSettings:
    projects_root: str
    remember_last_page: bool = True
    remember_window_size: bool = True
    remember_last_model_config: bool = True
    custom_title_bar_enabled: bool = True
    collapsible_sidebar_enabled: bool = True


def build_settings_description(settings: AppSettings) -> str:
    return (
        "Aktualne ustawienia aplikacji:\n\n"
        f"- Domyslny folder projektow: {settings.projects_root}\n"
        f"- Zapamietywanie ostatniej strony: {'tak' if settings.remember_last_page else 'nie'}\n"
        f"- Zapamietywanie rozmiaru okna: {'tak' if settings.remember_window_size else 'nie'}\n"
        f"- Zapamietywanie ostatniej konfiguracji modelu: {'tak' if settings.remember_last_model_config else 'nie'}\n"
        f"- Wlasny pasek tytulu: {'tak' if settings.custom_title_bar_enabled else 'nie'}\n"
        f"- Zwijany pasek boczny: {'tak' if settings.collapsible_sidebar_enabled else 'nie'}"
    )