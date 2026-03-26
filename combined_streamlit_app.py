
import io
import os
import csv
import math
import zipfile
from glob import glob
from pathlib import Path

import streamlit as st

try:
    import fitz
except ImportError:
    fitz = None

try:
    from PyPDF2 import PdfReader, PdfWriter
except ImportError:
    PdfReader = None
    PdfWriter = None

try:
    from pypdf import PdfReader as PypdfReader, PdfWriter as PypdfWriter
except ImportError:
    PypdfReader = None
    PypdfWriter = None


def require_module(ok, name):
    if not ok:
        st.error(f"Missing dependency: {name}. Please install it first.")
        st.stop()


def sanitize_name(name: str) -> str:
    keep = []
    for ch in name:
        if ch.isalnum() or ch in ('-', '_', '.', ' '):
            keep.append(ch)
        else:
            keep.append('_')
    return ''.join(keep)


def add_bytes_to_zip(zf: zipfile.ZipFile, arcname: str, data: bytes):
    zf.writestr(arcname.replace('\\', '/'), data)


def extract_images_from_pdf_bytes(pdf_name: str, pdf_bytes: bytes):
    require_module(fitz is not None, 'PyMuPDF')
    results = []
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    for page_index in range(len(doc)):
        page = doc.load_page(page_index)
        images = page.get_images(full=True)
        for img_index, img in enumerate(images, start=1):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image['image']
            image_ext = base_image['ext']
            image_name = f"{Path(pdf_name).stem}_page{page_index + 1}_img{img_index}.{image_ext}"
            results.append((image_name, image_bytes))
    doc.close()
    return results


def split_pdf_bytes(pdf_name: str, pdf_bytes: bytes, pages_per_split: int):
    require_module(PdfReader is not None and PdfWriter is not None, 'PyPDF2')
    reader = PdfReader(io.BytesIO(pdf_bytes))
    total_pages = len(reader.pages)
    outputs = []
    split_count = math.ceil(total_pages / pages_per_split) if total_pages else 0
    for split_num in range(1, split_count + 1):
        start_page = (split_num - 1) * pages_per_split
        end_page = min(split_num * pages_per_split, total_pages)
        writer = PdfWriter()
        for page_num in range(start_page, end_page):
            writer.add_page(reader.pages[page_num])
        bio = io.BytesIO()
        writer.write(bio)
        out_name = f"{split_num}_{Path(pdf_name).stem}_split{pages_per_split}.pdf"
        outputs.append((out_name, bio.getvalue()))
    return outputs, total_pages


def merge_pdf_files(uploaded_files):
    require_module(PdfReader is not None and PdfWriter is not None, 'PyPDF2')
    writer = PdfWriter()
    count = 0
    for up in sorted(uploaded_files, key=lambda x: x.name.lower()):
        reader = PdfReader(io.BytesIO(up.getvalue()))
        for page in reader.pages:
            writer.add_page(page)
        count += 1
    bio = io.BytesIO()
    writer.write(bio)
    return bio.getvalue(), count


def number_uploaded_files(uploaded_files, digits: int = 3):
    outputs = []
    for idx, up in enumerate(sorted(uploaded_files, key=lambda x: x.name.lower()), start=1):
        new_name = f"{idx:0{digits}d}_{up.name}"
        outputs.append((new_name, up.getvalue()))
    return outputs


def compute_page_size_mm(first_page):
    crop_box = getattr(first_page, 'cropbox', None)
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


def unique_name(existing: set, filename: str) -> str:
    path = Path(filename)
    stem = path.stem
    suffix = path.suffix
    candidate = filename
    counter = 1
    while candidate in existing:
        candidate = f"{stem}_{counter}{suffix}"
        counter += 1
    existing.add(candidate)
    return candidate


def file_prefixer_outputs(
    uploaded_files,
    prefix,
    add_suffix,
    suffix_after_prefix,
    use_divider,
    divider_value,
    create_csv,
    create_druck_folder,
    add_page_size,
    use_suffix_seiten,
    split_enabled,
    split_pages,
):
    require_module(PdfReader is not None and PdfWriter is not None, 'PyPDF2')
    outputs = []
    csv_rows = []
    used_names = set()
    label = 'Seiten' if use_suffix_seiten else 'Ex'

    for up in sorted(uploaded_files, key=lambda x: x.name.lower()):
        filename = up.name
        old_bytes = up.getvalue()
        name_without_ext = Path(filename).stem
        ext = Path(filename).suffix
        new_base = prefix
        page_count_value = ''
        divided_pages_value = ''
        suffix_part = ''
        page_size_part = ''
        new_ext = ext

        if filename.lower().endswith('.pdf'):
            try:
                pdf_reader = PdfReader(io.BytesIO(old_bytes))
                page_count = len(pdf_reader.pages)
                first_page = pdf_reader.pages[0] if page_count else None
                if first_page and add_page_size:
                    width_mm, height_mm = compute_page_size_mm(first_page)
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
            except Exception:
                new_base = prefix + filename
                new_ext = ''
        else:
            if add_suffix and suffix_after_prefix:
                suffix_part = f"0_{label}_"
                new_base += suffix_part
            new_base += filename
            new_ext = ''

        new_filename = new_base + new_ext if new_ext else new_base
        if not Path(new_filename).suffix and Path(filename).suffix:
            new_filename += Path(filename).suffix
        new_filename = sanitize_name(new_filename)
        new_filename = unique_name(used_names, new_filename)

        folder_prefix = 'CHEKC_druck_pdf/' if create_druck_folder else ''
        outputs.append((folder_prefix + new_filename, old_bytes))

        if split_enabled and split_pages > 0 and filename.lower().endswith('.pdf'):
            split_outs, _ = split_pdf_bytes(filename, old_bytes, split_pages)
            for split_name, split_bytes in split_outs:
                outputs.append((f"split/{split_name}", split_bytes))

        if create_csv:
            csv_rows.append([
                filename,
                Path(new_filename).name,
                prefix,
                suffix_part,
                page_size_part,
                name_without_ext,
                page_count_value,
                divided_pages_value,
                ext,
            ])

    csv_bytes = None
    if create_csv:
        bio = io.StringIO()
        writer = csv.writer(bio, delimiter=';')
        writer.writerow([
            'Original', 'Neuer Name', 'Praefix', 'Suffix', 'Seitengröße',
            'Name ohne Ext', 'Seitenanzahl', 'Geteilte Seiten', 'Endung'
        ])
        writer.writerows(csv_rows)
        csv_bytes = bio.getvalue().encode('cp1252', errors='replace')
    return outputs, csv_bytes


def create_umschlag_outputs(uploaded_files):
    reader_cls = PypdfReader if PypdfReader is not None else PdfReader
    writer_cls = PypdfWriter if PypdfWriter is not None else PdfWriter
    require_module(reader_cls is not None and writer_cls is not None, 'pypdf or PyPDF2')

    outputs = []
    for up in sorted(uploaded_files, key=lambda x: x.name.lower()):
        if not up.name.lower().endswith('.pdf'):
            continue

        reader = reader_cls(io.BytesIO(up.getvalue()))
        total = len(reader.pages)
        if total == 0:
            continue

        filename = up.name
        if writer_cls is PypdfWriter and reader_cls is PypdfReader:
            ug_writer = PypdfWriter(clone_from=reader)
            content_writer = PypdfWriter(clone_from=reader)
        else:
            ug_writer = writer_cls()
            content_writer = writer_cls()

        if total <= 3:
            for page in reader.pages:
                ug_writer.add_page(page)
        else:
            ug_writer.add_page(reader.pages[0])
            ug_writer.add_page(reader.pages[1])
            ug_writer.add_page(reader.pages[-2])
            ug_writer.add_page(reader.pages[-1])
            for i in range(2, total - 2):
                content_writer.add_page(reader.pages[i])

        ug_bio = io.BytesIO()
        ug_writer.write(ug_bio)
        outputs.append((f"umschlag/UG_{filename}", ug_bio.getvalue()))

        if len(content_writer.pages) > 0:
            inhalt_bio = io.BytesIO()
            content_writer.write(inhalt_bio)
            outputs.append((f"umschlag/Inhalt_{filename}", inhalt_bio.getvalue()))
    return outputs


def build_zip(file_pairs):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, data in file_pairs:
            add_bytes_to_zip(zf, name, data)
    bio.seek(0)
    return bio.getvalue()


def papier_berechnen(pw, ph, rand_aktiv, rw, rh, sx, sy, sw, sh, menge, prefix, pages_total=None, cover_sep=False):
    rw = rw if rand_aktiv else 0
    rh = rh if rand_aktiv else 0

    bogen_cover = None
    bogen_innen = None
    if prefix == 'b':
        broschueren = menge
        if cover_sep:
            if pages_total < 4:
                raise ValueError("Bei Umschlag separat muss die Seitenzahl mindestens 4 sein.")
            pages_cover = 4
            pages_innen = max(pages_total - pages_cover, 0)
            bogen_cover = broschueren
            bogen_innen = broschueren * math.ceil(pages_innen / 4)
            menge = bogen_cover + bogen_innen
        else:
            menge = broschueren * math.ceil(pages_total / 4)

    pw_calc = pw * 2 if prefix == 'b' else pw
    ph_calc = ph

    eff_w = pw_calc + 2 * rw
    eff_h = ph_calc + 2 * rh

    nx = int((sw + sx) // (eff_w + sx)) if (eff_w + sx) > 0 else 0
    ny = int((sh + sy) // (eff_h + sy)) if (eff_h + sy) > 0 else 0
    nutzen = nx * ny
    druckbogen_gesamt = math.ceil(menge / nutzen) if nutzen > 0 else 0
    rest_lr = (sw - (nx * eff_w + (nx - 1) * sx)) / 2 if nx > 0 else 0
    rest_ob = (sh - (ny * eff_h + (ny - 1) * sy)) / 2 if ny > 0 else 0

    out = {
        'pw_calc': pw_calc,
        'ph_calc': ph_calc,
        'nutzen': nutzen,
        'bogen_gesamt': menge,
        'druckbogen_gesamt': druckbogen_gesamt,
        'rest_lr': rest_lr,
        'rest_ob': rest_ob,
        'nx': nx,
        'ny': ny,
        'bogen_cover': bogen_cover,
        'bogen_innen': bogen_innen,
    }
    if prefix == 'b' and cover_sep:
        out['druckbogen_cover'] = math.ceil(bogen_cover / nutzen) if nutzen > 0 else 0
        out['druckbogen_innen'] = math.ceil(bogen_innen / nutzen) if nutzen > 0 else 0
    return out


st.set_page_config(page_title='Combined PDF Tools', layout='wide')
st.title('Combined PDF Tools - Streamlit')
st.caption('Converted from the original tkinter tools into a browser-based Streamlit app.')

main_tabs = st.tabs([
    'Image Extractor', 'Numerieren', 'PDF Split Fast', 'PDF Tools',
    'PDF Merge', 'PDF Split Alt', 'Papier Rechner', 'Umschlag'
])

with main_tabs[0]:
    st.subheader('PDF Image Extractor')
    uploaded = st.file_uploader('Upload one or more PDF files', type=['pdf'], accept_multiple_files=True, key='extractor_upload')
    if st.button('Extract images', key='extract_btn'):
        if not uploaded:
            st.warning('Please upload at least one PDF.')
        else:
            outputs = []
            logs = []
            for up in uploaded:
                imgs = extract_images_from_pdf_bytes(up.name, up.getvalue())
                logs.append(f"{up.name}: {len(imgs)} images")
                for img_name, img_bytes in imgs:
                    outputs.append((f"extract/{img_name}", img_bytes))
            st.text('\n'.join(logs) if logs else 'No images found.')
            if outputs:
                z = build_zip(outputs)
                st.download_button('Download extracted images ZIP', data=z, file_name='extracted_images.zip', mime='application/zip')
            else:
                st.info('No images found in the uploaded PDFs.')

with main_tabs[1]:
    st.subheader('Numerieren')
    uploaded = st.file_uploader('Upload files to renumber', accept_multiple_files=True, key='num_upload')
    digits = st.number_input('Digits', min_value=2, max_value=6, value=3, step=1)
    if st.button('Number files', key='num_btn'):
        if not uploaded:
            st.warning('Please upload files.')
        else:
            outs = number_uploaded_files(uploaded, digits=int(digits))
            preview = '\n'.join([name for name, _ in outs[:50]])
            st.text(preview)
            st.download_button('Download numbered files ZIP', data=build_zip(outs), file_name='numbered_files.zip', mime='application/zip')

with main_tabs[2]:
    st.subheader('PDF Split Fast')
    uploaded = st.file_uploader('Upload PDF', type=['pdf'], key='split_fast_upload')
    pages_per_split = st.number_input('Pages per file', min_value=1, max_value=5000, value=10, step=1, key='split_fast_pages')
    if st.button('Split PDF', key='split_fast_btn'):
        if not uploaded:
            st.warning('Please upload a PDF.')
        else:
            outs, total_pages = split_pdf_bytes(uploaded.name, uploaded.getvalue(), int(pages_per_split))
            st.success(f'{uploaded.name}: {total_pages} pages, {len(outs)} output files.')
            st.download_button('Download split ZIP', data=build_zip(outs), file_name='split_fast.zip', mime='application/zip')

with main_tabs[3]:
    st.subheader('Datei-Präfixer')
    uploaded = st.file_uploader('Upload files', accept_multiple_files=True, key='prefix_upload')
    col1, col2, col3 = st.columns(3)
    with col1:
        prefix = st.text_input('Präfix', value='Auftragsnummer_')
        add_suffix = st.checkbox('Seitenanzahl-Suffix hinzufügen')
        suffix_after_prefix = st.checkbox('Suffix direkt nach Präfix')
    with col2:
        use_divider = st.checkbox('Seitenanzahl teilen durch')
        divider_value = st.number_input('Teiler', min_value=1, max_value=1000, value=2, step=1)
        add_page_size = st.checkbox('Seitengröße im Dateinamen speichern')
    with col3:
        create_csv = st.checkbox('CSV-Bericht erstellen', value=True)
        create_druck_folder = st.checkbox("In 'CHEKC_druck_pdf' Ordner legen")
        use_suffix_seiten = st.checkbox("'Seiten' statt 'Ex' verwenden")

    split_enabled = st.checkbox('PDF-Dateien nach X Seiten splitten')
    split_pages = st.number_input('Split-Seiten', min_value=1, max_value=5000, value=10, step=1, disabled=not split_enabled)

    if st.button('Verarbeitung starten', key='prefix_btn'):
        if not uploaded:
            st.warning('Please upload files.')
        else:
            outs, csv_bytes = file_prefixer_outputs(
                uploaded_files=uploaded,
                prefix=prefix,
                add_suffix=add_suffix,
                suffix_after_prefix=suffix_after_prefix,
                use_divider=use_divider,
                divider_value=int(divider_value),
                create_csv=create_csv,
                create_druck_folder=create_druck_folder,
                add_page_size=add_page_size,
                use_suffix_seiten=use_suffix_seiten,
                split_enabled=split_enabled,
                split_pages=int(split_pages),
            )
            if csv_bytes is not None:
                outs.append(('datei_bericht.csv', csv_bytes))
            st.success(f'{len(uploaded)} files processed.')
            st.download_button('Download result ZIP', data=build_zip(outs), file_name='pdf_tools_output.zip', mime='application/zip')

with main_tabs[4]:
    st.subheader('PDF Merge')
    uploaded = st.file_uploader('Upload PDFs to merge', type=['pdf'], accept_multiple_files=True, key='merge_upload')
    if st.button('Merge PDFs', key='merge_btn'):
        if not uploaded:
            st.warning('Please upload PDF files.')
        else:
            merged_bytes, count = merge_pdf_files(uploaded)
            st.success(f'{count} PDF files merged.')
            st.download_button('Download merged PDF', data=merged_bytes, file_name='merged.pdf', mime='application/pdf')

with main_tabs[5]:
    st.subheader('PDF Split Alt')
    uploaded = st.file_uploader('Upload PDF', type=['pdf'], key='split_alt_upload')
    pages_per_split = st.number_input('Pages per file', min_value=1, max_value=5000, value=10, step=1, key='split_alt_pages')
    if st.button('Split PDF (Alt)', key='split_alt_btn'):
        if not uploaded:
            st.warning('Please upload a PDF.')
        else:
            outs, total_pages = split_pdf_bytes(uploaded.name, uploaded.getvalue(), int(pages_per_split))
            st.info(f'{uploaded.name}: {total_pages} pages.')
            st.download_button('Download split ZIP', data=build_zip(outs), file_name='split_alt.zip', mime='application/zip')

with main_tabs[6]:
    st.subheader('Druck-Papier Nutzen Rechner')
    din_formate = {
        'DIN A0': (841, 1189), 'DIN A1': (594, 841), 'DIN A2': (420, 594),
        'DIN A3': (297, 420), 'DIN A4': (210, 297), 'DIN A5': (148, 210),
        'DIN A6': (105, 148), 'DIN A7': (74, 105), 'DIN A8': (52, 74),
        'DIN A9': (37, 52), 'DIN A10': (26, 37)
    }
    p_tabs = st.tabs(['Einzelprodukt', 'Broschüre'])

    with p_tabs[0]:
        fmt = st.selectbox('Produktgröße', list(din_formate.keys()), index=4, key='e_fmt')
        dw, dh = din_formate[fmt]
        c1, c2 = st.columns(2)
        with c1:
            pw = st.number_input('Breite (mm)', value=int(dw), key='e_pw')
            rw_active = st.checkbox('Beschnitt aktiv', value=True, key='e_rw_active')
            rw = st.number_input('Beschnitt Breite', value=3.0, key='e_rw')
            sx = st.number_input('Steg horizontal', value=0.0, key='e_sx')
            sw = st.number_input('Druckbogen Breite', value=450.0, key='e_sw')
            menge = st.number_input('Stück', value=1000, key='e_menge')
        with c2:
            ph = st.number_input('Höhe (mm)', value=int(dh), key='e_ph')
            rh = st.number_input('Beschnitt Höhe', value=3.0, key='e_rh')
            sy = st.number_input('Steg vertikal', value=0.0, key='e_sy')
            sh = st.number_input('Druckbogen Höhe', value=320.0, key='e_sh')
        if st.button('Berechnen', key='e_calc'):
            res = papier_berechnen(float(pw), float(ph), rw_active, float(rw), float(rh), float(sx), float(sy), float(sw), float(sh), int(menge), 'e')
            st.json(res)

    with p_tabs[1]:
        fmt = st.selectbox('Endformat', list(din_formate.keys()), index=4, key='b_fmt')
        dw, dh = din_formate[fmt]
        c1, c2 = st.columns(2)
        with c1:
            pw = st.number_input('Breite (mm)', value=int(dw), key='b_pw')
            rw_active = st.checkbox('Beschnitt aktiv', value=True, key='b_rw_active')
            rw = st.number_input('Beschnitt Breite', value=3.0, key='b_rw')
            sx = st.number_input('Steg horizontal', value=0.0, key='b_sx')
            sw = st.number_input('Druckbogen Breite', value=450.0, key='b_sw')
            menge = st.number_input('Broschüren', value=1000, key='b_menge')
            pages_total = st.number_input('Seiten', min_value=1, value=16, key='b_pages')
        with c2:
            ph = st.number_input('Höhe (mm)', value=int(dh), key='b_ph')
            rh = st.number_input('Beschnitt Höhe', value=3.0, key='b_rh')
            sy = st.number_input('Steg vertikal', value=0.0, key='b_sy')
            sh = st.number_input('Druckbogen Höhe', value=320.0, key='b_sh')
            cover_sep = st.checkbox('Umschlag anderes Papier (4 Seiten separat)', value=False, key='b_cover')
            st.write(f"Bogen je Broschüre: {math.ceil(int(pages_total) / 4)}")
        if st.button('Berechnen', key='b_calc'):
            try:
                res = papier_berechnen(float(pw), float(ph), rw_active, float(rw), float(rh), float(sx), float(sy), float(sw), float(sh), int(menge), 'b', pages_total=int(pages_total), cover_sep=cover_sep)
                st.json(res)
            except Exception as e:
                st.error(str(e))

with main_tabs[7]:
    st.subheader('Umschlag Tool')
    uploaded = st.file_uploader('Upload PDF files', type=['pdf'], accept_multiple_files=True, key='umschlag_upload')
    if st.button('Umschlag erzeugen', key='umschlag_btn'):
        if not uploaded:
            st.warning('Please upload at least one PDF.')
        else:
            outs = create_umschlag_outputs(uploaded)
            if not outs:
                st.info('No output generated.')
            else:
                st.success(f'{len(outs)} files generated.')
                st.download_button('Download Umschlag ZIP', data=build_zip(outs), file_name='umschlag_output.zip', mime='application/zip')
