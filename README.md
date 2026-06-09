# Annotatio

Prosty desktopowy szkielet aplikacji do annotacji obrazow zbudowany w Tkinter, z warstwowym podzialem na `gui`, `model`, `controller` i `database`.

## Struktura

- `app.py` - entrypoint aplikacji
- `gui/` - okna, strony i dialogi Tkinter
- `model/` - encje i logika aplikacji
- `controller/` - spina widoki z logika
- `database/` - SQLite oraz repozytorium danych

## Funkcje

- ekran startowy z opisem aplikacji
- sidebar: Projects, Settings, Info
- tworzenie projektow i etykiet
- lista projektow z podgladem, liczba obrazow, annotacji i data zmiany
- tworzenie taskow z folderu obrazow
- podglad taska z przechodzeniem po obrazach
- dodawanie / ukrywanie / usuwanie annotacji
- proste automatyczne etykietowanie przyciskiem modelowym
- eksport projektu do JSON, CSV albo TXT
- zapis sesji i danych do SQLite

## Uruchomienie

```powershell
python app.py
```

## Opcjonalna biblioteka do lepszego podgladu obrazow

Jesli chcesz miec obsluge JPG/JPEG i lepsze skalowanie podgladu, doinstaluj Pillow:

```powershell
pip install -r requirements.txt
```# Annotatio 2

Prosty desktopowy MVP do zarządzania projektami annotacyjnymi dla AI, napisany warstwowo:

- `gui/` - widoki Tkinter i dialogi
- `controller/` - przepływ aplikacji i nawigacja
- `model/` - encje i logika biznesowa
- `database/` - SQLite i repozytorium danych

## Uruchomienie

```powershell
python app.py
```

## Co działa

- ekran startowy z opisem aplikacji
- pasek boczny `Projects`, `Settings`, `Info`
- tworzenie projektów z typem projektu i definicjami etykiet
- tworzenie tasków na podstawie folderu z obrazami
- lista projektów i tasków z podglądem pierwszego obrazu
- widok taska z nawigacją po zdjęciach
- dodawanie, ukrywanie i usuwanie labeli dla bieżącego zdjęcia
- usuwanie zdjęcia z aktywnego datasetu
- proste auto-labelowanie przez przypisanie etykiety projektowej
- eksport datasetu do struktury `COCO`, `YOLO`, `Pascal VOC`
- zapis sesji aplikacji w SQLite

## Uwaga

Ten MVP przechowuje etykiety na poziomie przypisania do zdjęcia. Nie zawiera jeszcze edytora geometrii dla bounding boxów, masek ani keypointów, ale przygotowuje strukturę pod dalszą rozbudowę.