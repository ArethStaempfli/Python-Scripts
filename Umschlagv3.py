import os
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Any
from pypdf import PdfReader, PdfWriter
from PIL import Image, ImageTk


APP_TITLE = "PDF Umschlag Tool"
CONFIG_DIRNAME = "settings"
CONFIG_FILENAME = "config.json"
LOGO_FILENAME = "logo.jpg"
UMSCHLAG_FOLDER_NAME = "umschlag"
SETTINGS_VERSION = 1

BG_MAIN = "#add8e6"
COLOR_OK = "#4CAF50"

# -------------------- Settings helpers --------------------
def get_settings_folder() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    folder = os.path.join(base, CONFIG_DIRNAME)
    os.makedirs(folder, exist_ok=True)
    return folder

def get_settings_path() -> str:
    return os.path.join(get_settings_folder(), CONFIG_FILENAME)

def default_settings() -> Dict[str, Any]:
    return {
        "settings_version": SETTINGS_VERSION,
        "default_input_folder": "",
    }

def load_settings() -> Dict[str, Any]:
    try:
        with open(get_settings_path(), "r", encoding="utf-8") as f:
            return {**default_settings(), **json.load(f)}
    except Exception:
        return default_settings()

def save_settings(data: Dict[str, Any]) -> None:
    with open(get_settings_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# -------------------- Logo loader --------------------
def load_logo() -> ImageTk.PhotoImage | None:
    logo_path = os.path.join(get_settings_folder(), LOGO_FILENAME)
    try:
        if os.path.exists(logo_path):
            img = Image.open(logo_path)
            img = img.resize((80, 80), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img)
    except Exception as e:
        print(f"Fehler beim Laden des Logos: {e}")
    return None

# -------------------- Umschlag logic (Updated to preserve OutputIntent) --------------------
def create_umschlag_pdfs(pdf_path: str, out_folder: str) -> None:
    try:
        reader = PdfReader(pdf_path)
    except Exception as e:
        print(f"Fehler beim Öffnen {pdf_path}: {e}")
        return

    total = len(reader.pages)
    if total == 0:
        return

    filename = os.path.basename(pdf_path)

    # Clone document root to preserve OutputIntents, Info, ID
    ug_writer = PdfWriter(clone_from=reader)  # Key change: clones catalog
    content_writer = PdfWriter(clone_from=reader)

    if total <= 3:
        # Alle Seiten gehen in UG
        for page in reader.pages:
            ug_writer.add_page(page)
    else:
        # Erste 2 + letzte 2 → UG
        ug_writer.add_page(reader.pages[0])
        ug_writer.add_page(reader.pages[1])
        ug_writer.add_page(reader.pages[-2])
        ug_writer.add_page(reader.pages[-1])

        # Seiten dazwischen → Inhalt
        for i in range(2, total - 2):
            content_writer.add_page(reader.pages[i])

    # Write UG
    ug_path = os.path.join(out_folder, f"UG_{filename}")
    with open(ug_path, "wb") as f:
        ug_writer.write(f)

    # Write Inhalt if needed
    if content_writer.pages:
        inhalt_path = os.path.join(out_folder, f"Inhalt_{filename}")
        with open(inhalt_path, "wb") as f:
            content_writer.write(f)

# -------------------- Processing --------------------
def process_files():
    input_dir = input_var.get()

    if not input_dir:
        messagebox.showerror("Fehler", "Bitte einen Eingabeordner auswählen")
        return

    umschlag_dir = os.path.join(input_dir, UMSCHLAG_FOLDER_NAME)
    os.makedirs(umschlag_dir, exist_ok=True)

    pdf_files = [
        f for f in os.listdir(input_dir)
        if f.lower().endswith(".pdf")
        and not f.startswith(("UG_", "Inhalt_"))
        and os.path.isfile(os.path.join(input_dir, f))
    ]

    total_files = len(pdf_files)
    if total_files == 0:
        messagebox.showinfo("Info", "Keine neuen PDF-Dateien gefunden")
        return

    progress_bar["maximum"] = total_files
    progress_bar["value"] = 0

    for idx, filename in enumerate(pdf_files, start=1):
        status_label.config(text=f"Verarbeite {idx} / {total_files}: {filename}")
        root.update_idletasks()

        create_umschlag_pdfs(
            os.path.join(input_dir, filename),
            umschlag_dir
        )

        progress_bar["value"] = idx

    save_settings({
        "settings_version": SETTINGS_VERSION,
        "default_input_folder": input_var.get(),
    })

    status_label.config(text="Fertig")
    messagebox.showinfo(
        "Fertig",
        f"{total_files} PDF-Dateien verarbeitet.\n"
        f"Ergebnisordner:\n{umschlag_dir}"
    )

# -------------------- GUI --------------------
settings = load_settings()

root = tk.Tk()
root.title(APP_TITLE)
root.geometry("520x420")
root.configure(bg=BG_MAIN)

# --- Logo ---
logo = load_logo()
if logo:
    logo_label = tk.Label(root, image=logo, bg=BG_MAIN)
    logo_label.image = logo
    logo_label.pack(pady=(15, 5))

input_var = tk.StringVar(value=settings["default_input_folder"])

tk.Label(
    root,
    text="Eingabeordner",
    bg=BG_MAIN,
    font=("Arial", 10, "bold")
).pack(pady=(10, 0))

tk.Entry(root, textvariable=input_var, width=60).pack()

tk.Button(
    root,
    text="Durchsuchen",
    command=lambda: input_var.set(filedialog.askdirectory())
).pack(pady=5)

# --- Progress ---
progress_bar = ttk.Progressbar(
    root,
    length=400,
    mode="determinate"
)
progress_bar.pack(pady=(25, 5))

status_label = tk.Label(
    root,
    text="Bereit",
    bg=BG_MAIN,
    font=("Arial", 9)
)
status_label.pack()

tk.Button(
    root,
    text="UMSCHLAG ERZEUGEN",
    command=process_files,
    bg=COLOR_OK,
    fg="white",
    font=("Arial", 12, "bold"),
    width=24,
    height=2,
).pack(pady=25)

root.mainloop()