import streamlit as st
from pypdf import PdfReader, PdfWriter
import io
import zipfile

st.title("📄 PDF Umschlag Tool für Alex Dietrich Stämpfli")

uploaded_file = st.file_uploader("Upload PDF", type="pdf")

if uploaded_file is not None:
    reader = PdfReader(uploaded_file)
    total = len(reader.pages)
    st.success(f"📖 {total} pages loaded")
    
    if st.button("✨ Erzeugen Umschlag!", type="primary"):
        ug_writer = PdfWriter(clone_from=reader)
        content_writer = PdfWriter(clone_from=reader)
        
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
        
        # Individual downloads
        ug_bytes = io.BytesIO()
        ug_writer.write(ug_bytes)
        ug_bytes.seek(0)
        st.download_button("📁 UG_output.pdf", ug_bytes.getvalue(), "UG_output.pdf")
        
        if content_writer.pages:
            content_bytes = io.BytesIO()
            content_writer.write(content_bytes)
            content_bytes.seek(0)
            st.download_button("📄 Inhalt_output.pdf", content_bytes.getvalue(), "Inhalt_output.pdf")
        
        # ZIP (fixed)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("UG_output.pdf", ug_bytes.getvalue())
            if content_writer.pages:
                zf.writestr("Inhalt_output.pdf", content_bytes.getvalue())
        st.download_button("🗜️ Download ZIP", zip_buffer.getvalue(), "umschlag.zip")
