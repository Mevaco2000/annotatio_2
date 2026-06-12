from __future__ import annotations


class LabelsChecksService:
    def get_description(self) -> str:
        return (
            "Modul weryfikacji annotacji jest przygotowany jako osobny serwis.\n\n"
            "Docelowo w tym miejscu beda uruchamiane reguly sprawdzajace jakosc labeli, "
            "spojnosc typow annotacji, brakujace punkty, niepoprawne bounding boxy oraz inne problemy w danych."
        )