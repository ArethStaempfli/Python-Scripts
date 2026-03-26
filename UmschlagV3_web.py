import streamlit as st
from pypdf import PdfReader, PdfWriter
import io
import zipfile
from typing import List

st.title("📄 PDF Umschlag Tool (Web)")

uploaded_file = st.file_uploader("Upload PDF", type="pdf")

if uploaded_file:
    reader = PdfReader(uploaded_file)
    total_pages = len(reader.pages)
    st.success(f"Loaded: {total_pages} pages")

    if st.button("Erzeugen Umschlag!"):
        # UG: first 2 + last 2 (or all if <=3)
        ug_writer = PdfWriter(clone_from=reader)
        content_writer = PdfWriter(clone_from=reader)

        if total_pages <= 3:
            for page in reader.pages:
                ug_writer.add_page(page)
        else:
            ug_writer.add_page(reader.pages[0])
            ug_writer.add_page(reader.pages[1])
            ug_writer.add_page(reader.pages[-2])
            ug_writer.add_page(reader.pages[-1])
            for i in range(2, total_pages - 2):
                content_writer.add_page(reader.pages[i])

        # ZIP outputs
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            zip_file.writestr("UG_output.pdf", ug_writer.write(io.BytesIO()).getvalue())
            if content_writer.pages:
                zip_file.writestr("Inhalt_output.pdf", content_writer.write(io.BytesIO()).getvalue())

        st.download_button(
            "Download ZIP (UG + Inhalt)",
            zip_buffer.getvalue(),
            "umschlag.zip",
            "application/zip"
        )

        # Preview first page
        st.subheader("Preview (UG first page)")
        pdf_bytes = ug_writer.write(io.BytesIO()).getvalue()
        st.download_button("Download UG PDF", pdf_bytes, "UG_output.pdf", "application/pdf")

if __name__ == "__main__":
    pass  # Streamlit handles run