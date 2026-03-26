import os
import csv
import json
import shutil
import streamlit as st
from typing import Dict, Any, List, Tuple
from PyPDF2 import PdfReader, PdfWriter
import time

# Constants (unchanged)
APP_TITLE = "Datei-Präfixer mit PDF-Seitenzähler (Streamlit)"
CONFIG_DIRNAME = "settings"
CONFIG_FILENAME = "file_prefixer_config.json"
LOGO_FILENAME = "logo.jpg"
DRUCK_FOLDER_NAME = "CHEKC_druck_pdf"
SPLIT_FOLDER_NAME = "split"
CSV_FILENAME = "datei_bericht.csv"
SETTINGS_VERSION = 1

BG_MAIN = "#add8e6"
COLOR_OK = "#4CAF50"
COLOR_DANGER = "#D32F2F"
COLOR_ACCENT = "#9C27B0"
COLOR_TITLE = "#1976D2"

CSV_HEADERS = [
    "Original", "Neuer Name", "Praefix", "Suffix", "Seitengröße",
    "Name ohne Ext", "Seitenanzahl", "Geteilte Seiten", "Endung"
]

# Settings helpers (mostly unchanged)
@st.cache_data
def get_settings_folder() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    settings_folder = os.path.join(script_dir, CONFIG_DIRNAME)
    os.makedirs(settings_folder, exist_ok=True)
    return settings_folder

def get_settings_config_path() -> str:
    return os.path.join(get_settings_folder(), CONFIG_FILENAME)

def default_settings_dict() -> Dict[str, Any]:
    return {
        "settings_version": SETTINGS_VERSION,
        "default_prefix": "Auftragsnummer_",
        "default_suffix": False,
        "default_suffix_after_prefix": False,
        "default_divider": False,
        "default_divider_value": 2,
        "default_page_size": False,
        "default_csv": False,
        "default_druck": False,
        "default_input_folder": "",
        "default_output_folder": "",
        "default_suffix_label_seiten": False,
        "default_split": False,
        "default_split_pages": 10,
        "options_order": ["suffix", "suffix_label_seiten", "suffix_after_prefix", "divider", "page_size", "csv", "druck", "split"]
    }

def load_settings() -> Dict[str, Any]:
    config_path = get_settings_config_path()
    base_defaults = default_settings_dict()
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("settings_version", 0) < SETTINGS_VERSION:
            data["settings_version"] = SETTINGS_VERSION
        return {**base_defaults, **data}
    except (FileNotFoundError, json.JSONDecodeError):
        return base_defaults

def save_settings(settings: Dict[str, Any]) -> None:
    settings["settings_version"] = SETTINGS_VERSION
    config_path = get_settings_config_path()
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    st.success("Einstellungen gespeichert!")

# Core helpers (unchanged)
def unique_path(folder: str, base_name: str, ext: str) -> str:
    candidate = os.path.join(folder, base_name + ext)
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base_name}_{counter}{ext}")
        counter += 1
    return candidate

def compute_page_size_mm(first_page) -> Tuple[int, int]:
    crop_box = getattr(first_page, "cropbox", None)
    if crop_box is not None:
        width_pt = float(crop_box.right) - float(crop_box.left)
        height_pt = float(crop_box.top) - float(crop_box.bottom)
    else:
        media_box = first_page.mediabox
        width_pt = float(media_box.width)
        height_pt = float(media_box.height)
    width_mm = round(width_pt * 25.4 / 72)
    height_mm = round(height_pt * 25.4 / 72)
    return width_mm, height_mm

def split_pdf_into_folder(pdf_path: str, split_folder: str, pages_per_part: int) -> None:
    if pages_per_part <= 0:
        return
    try:
        reader = PdfReader(pdf_path)
    except Exception as e:
        st.error(f"Fehler beim Öffnen für Split {pdf_path}: {e}")
        return
    total_pages = len(reader.pages)
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    part_index = 1
    for start in range(0, total_pages, pages_per_part):
        writer = PdfWriter()
        end = min(start + pages_per_part, total_pages)
        for page_num in range(start, end):
            writer.add_page(reader.pages[page_num])
        out_name = f"{base_name}_Teil{part_index}.pdf"
        out_path = os.path.join(split_folder, out_name)
        try:
            with open(out_path, "wb") as f_out:
                writer.write(f_out)
            st.info(f"Split erzeugt: {out_path}")
        except Exception as e:
            st.error(f"Fehler beim Schreiben Split-Datei {out_path}: {e}")
        part_index += 1

# Main processing function (adapted for Streamlit)
def process_files(
    input_folder: str, output_folder: str, prefix: str, add_suffix: bool,
    suffix_after_prefix: bool, use_divider: bool, divider_value: int,
    create_csv: bool, create_druck_folder: bool, add_page_size: bool,
    use_suffix_seiten: bool, csv_only_mode: bool, split_enabled: bool, split_pages: int,
    progress_callback
):
    if not os.path.exists(input_folder):
        st.error("Eingabeordner existiert nicht!")
        return 0
    os.makedirs(output_folder, exist_ok=True)
    if create_druck_folder and not csv_only_mode:
        druck_folder = os.path.join(output_folder, DRUCK_FOLDER_NAME)
        os.makedirs(druck_folder, exist_ok=True)
        target_folder = druck_folder
    else:
        target_folder = output_folder
    split_folder = os.path.join(output_folder, SPLIT_FOLDER_NAME)
    if split_enabled and not csv_only_mode:
        os.makedirs(split_folder, exist_ok=True)

    all_files = sorted([f for f in os.listdir(input_folder) if os.path.isfile(os.path.join(input_folder, f))])
    total_files = len(all_files)
    if total_files == 0:
        st.warning("Keine Dateien im Eingabeordner gefunden!")
        return 0

    processed_count = 0
    csv_data = []
    label = "Seiten" if use_suffix_seiten else "Ex"

    for i, filename in enumerate(all_files):
        old_file_path = os.path.join(input_folder, filename)
        progress_callback((i + 1) / total_files)
        st.info(f"Verarbeite {i+1}/{total_files}: {filename}")

        new_base = prefix
        suffix_part = ""
        page_size_part = ""
        name_without_ext, ext = os.path.splitext(filename)
        page_count_value = ""
        divided_pages_value = ""

        if filename.lower().endswith(".pdf"):
            try:
                pdf_reader = PdfReader(old_file_path)
                page_count = len(pdf_reader.pages)
                first_page = pdf_reader.pages[0]
                width_mm, height_mm = compute_page_size_mm(first_page)
                if add_page_size:
                    page_size_part = f"_{width_mm}x{height_mm}mm"
                page_count_value = page_count

                if add_suffix and suffix_after_prefix:
                    if use_divider and divider_value > 0:
                        divided_pages = page_count // divider_value
                        suffix_part = f"{divided_pages}_{label}_"
                        divided_pages_value = divided_pages
                    else:
                        suffix_part = f"{page_count}_{label}_"
                        divided_pages_value = page_count
                    new_base += suffix_part + page_size_part + name_without_ext
                    new_ext = ext
                else:
                    if add_page_size:
                        new_base += page_size_part
                    new_base += name_without_ext
                    if add_suffix and not suffix_after_prefix:
                        if use_divider and divider_value > 0:
                            divided_pages = page_count // divider_value
                            suffix_part = f"_{divided_pages}_{label}_"
                            divided_pages_value = divided_pages
                        else:
                            suffix_part = f"_{page_count}_{label}_"
                            divided_pages_value = page_count
                        new_base += suffix_part
                        new_ext = ext
            except Exception as e:
                st.error(f"Fehler beim Lesen {filename}: {e}")
                new_base = prefix + filename
                new_ext = ""
        else:
            if add_suffix and suffix_after_prefix:
                suffix_part = f"0_{label}_"
                new_base += suffix_part
            new_base += filename
            new_ext = ""

        if new_ext:
            new_file_path = unique_path(target_folder, new_base, new_ext)
        else:
            base, ext_tmp = os.path.splitext(new_base)
            new_file_path = unique_path(target_folder, base, ext_tmp)

        if not csv_only_mode:
            try:
                shutil.copy2(old_file_path, new_file_path)
                st.success(f"Kopiert: {filename} → {new_file_path}")
            except Exception as e:
                st.error(f"Fehler beim Kopieren {filename}: {e}")
                continue

            if split_enabled and split_pages > 0 and filename.lower().endswith(".pdf"):
                split_pdf_into_folder(old_file_path, split_folder, split_pages)

        processed_count += 1
        if create_csv:
            csv_data.append([filename, os.path.basename(new_file_path), prefix, suffix_part,
                             page_size_part, name_without_ext, page_count_value, divided_pages_value, ext])

    if create_csv:
        csv_path = os.path.join(output_folder, CSV_FILENAME)
        try:
            with open(csv_path, "w", newline="", encoding="cp1252") as csvfile:
                writer = csv.writer(csvfile, delimiter=";")
                writer.writerow(CSV_HEADERS)
                writer.writerows(csv_data)
            st.success(f"CSV-Bericht erstellt: {csv_path}")
        except Exception as e:
            st.error(f"CSV-Bericht konnte nicht erstellt werden: {e}")

    return processed_count

# Streamlit UI
st.set_page_config(page_title=APP_TITLE, layout="wide")
st.markdown(f"<h1 style='color: {COLOR_TITLE};'>{APP_TITLE}</h1>", unsafe_allow_html=True)

if "settings" not in st.session_state:
    st.session_state.settings = load_settings()
    st.session_state.progress = 0.0
    st.session_state.status = "Bereit"

settings = st.session_state.settings

# Sidebar for settings
with st.sidebar:
    st.header("Einstellungen")
    if st.button("Standardwerte laden", type="secondary"):
        st.session_state.settings = default_settings_dict()
        st.rerun()
    if st.button("Speichern", type="primary", use_container_width=True):
        save_settings(settings)
        st.session_state.settings = load_settings()
        st.rerun()

    st.subheader("Standardwerte")
    settings["default_input_folder"] = st.text_input("Eingabeordner", value=settings.get("default_input_folder", ""))
    settings["default_output_folder"] = st.text_input("Ausgabeordner", value=settings.get("default_output_folder", ""))
    settings["default_prefix"] = st.text_input("Präfix", value=settings.get("default_prefix", "Auftragsnummer_"))

# Main columns
col1, col2 = st.columns(2)

with col1:
    st.subheader("Eingabe")
    input_folder = st.text_input("Eingabeordner", value=settings.get("default_input_folder", ""), key="input")
    uploaded_files = st.file_uploader("Oder PDFs hochladen (Demo)", type="pdf", accept_multiple_files=True)

with col2:
    st.subheader("Ausgabe")
    output_folder = st.text_input("Ausgabeordner", value=settings.get("default_output_folder", ""), key="output")
    prefix = st.text_input("Präfix", value=settings.get("default_prefix", "Auftragsnummer_"), key="prefix")

# Options expander (respects order)
with st.expander("Optionen", expanded=True):
    order = settings.get("options_order", default_settings_dict()["options_order"])
    for key in order:
        if key == "suffix":
            settings["default_suffix"] = st.checkbox("Seitenanzahl-Suffix für PDFs hinzufügen", value=settings.get("default_suffix", False))
        elif key == "suffix_label_seiten":
            settings["default_suffix_label_seiten"] = st.checkbox("Suffix-Bezeichnung 'Seiten' statt 'Ex' verwenden", value=settings.get("default_suffix_label_seiten", False))
        elif key == "suffix_after_prefix":
            settings["default_suffix_after_prefix"] = st.checkbox("Suffix direkt nach Präfix", value=settings.get("default_suffix_after_prefix", False))
        elif key == "divider":
            col_d1, col_d2 = st.columns([3,1])
            with col_d1:
                settings["default_divider"] = st.checkbox("Seitenanzahl teilen durch:", value=settings.get("default_divider", False))
            with col_d2:
                divider_val = st.number_input("Teiler", min_value=1, value=settings.get("default_divider_value", 2), disabled=not settings["default_divider"])
                if settings["default_divider"]:
                    settings["default_divider_value"] = divider_val
        elif key == "page_size":
            settings["default_page_size"] = st.checkbox("Seitengröße im Dateinamen speichern", value=settings.get("default_page_size", False))
        elif key == "csv":
            settings["default_csv"] = st.checkbox("CSV-Bericht erstellen", value=settings.get("default_csv", False))
        elif key == "druck":
            settings["default_druck"] = st.checkbox(f"In '{DRUCK_FOLDER_NAME}' Ordner kopieren", value=settings.get("default_druck", False))
        elif key == "split":
            col_s1, col_s2 = st.columns([3,1])
            with col_s1:
                settings["default_split"] = st.checkbox("PDF-Dateien nach X Seiten splitten", value=settings.get("default_split", False))
            with col_s2:
                split_pages_val = st.number_input("X", min_value=1, value=settings.get("default_split_pages", 10), disabled=not settings["default_split"])
                if settings["default_split"]:
                    settings["default_split_pages"] = split_pages_val

# Process button
if st.button("VERARBEITUNG STARTEN", type="primary", use_container_width=True):
    if not input_folder or not output_folder:
        st.error("Bitte Eingabe- und Ausgabeordner ausfüllen!")
    else:
        add_suffix = settings["default_suffix"]
        suffix_after_prefix = settings["default_suffix_after_prefix"]
        use_divider = settings["default_divider"]
        divider_value = settings["default_divider_value"]
        create_csv = settings["default_csv"]
        create_druck_folder = settings["default_druck"]
        add_page_size = settings["default_page_size"]
        use_suffix_seiten = settings["default_suffix_label_seiten"]
        split_enabled = settings["default_split"]
        split_pages = settings["default_split_pages"]

        pdf_options_active = add_suffix or create_druck_folder or add_page_size or use_divider or use_suffix_seiten or split_enabled
        csv_only_mode = create_csv and not pdf_options_active

        progress_bar = st.progress(0.0)
        status_placeholder = st.empty()

        def progress_callback(value):
            progress_bar.progress(value)
            st.session_state.progress = value

        with st.spinner("Verarbeite Dateien..."):
            if uploaded_files:
                # Demo mode: save uploaded to temp input_folder
                temp_input = os.path.join(output_folder, "temp_input")
                os.makedirs(temp_input, exist_ok=True)
                for i, uploaded_file in enumerate(uploaded_files):
                    temp_path = os.path.join(temp_input, uploaded_file.name)
                    with open(temp_path, "wb") as f:
                        shutil.copyfileobj(uploaded_file, f)
                processed = process_files(temp_input, output_folder, prefix, add_suffix, suffix_after_prefix,
                                         use_divider, divider_value, create_csv, create_druck_folder,
                                         add_page_size, use_suffix_seiten, csv_only_mode, split_enabled, split_pages,
                                         progress_callback)
                shutil.rmtree(temp_input, ignore_errors=True)
            else:
                processed = process_files(input_folder, output_folder, prefix, add_suffix, suffix_after_prefix,
                                          use_divider, divider_value, create_csv, create_druck_folder,
                                          add_page_size, use_suffix_seiten, csv_only_mode, split_enabled, split_pages,
                                          progress_callback)

        status_placeholder.success(f"Fertig! {processed} Dateien verarbeitet.")
        st.balloons()

# Status
st.status(st.session_state.status)

if st.button("Reset Felder"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()