"""
AP Invoice Intake Helper — Streamlit Web App
=============================================
Place this file (app.py) in the SAME folder as TASKSPEC.py
then run:   streamlit run app.py
"""

import streamlit as st # type: ignore
import tempfile
import shutil
import csv
import io
from pathlib import Path
from collections import Counter
from TASKSPEC import (process_file, ensure_out_dirs, CSV_HEADERS, ocr_installed,)


#1. page config
st.set_page_config(page_title="AP Invoice Intake Helper", page_icon="🧾", layout="wide",)


#2. custom css: clean, professional look
st.markdown("""
<style>
    /* Hide default Streamlit header padding */
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }

    /* Status badge colours */
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }
    .badge-ok           { background: #d1fae5; color: #065f46; }
    .badge-review       { background: #fef3c7; color: #92400e; }
    .badge-duplicate    { background: #dbeafe; color: #1e40af; }
    .badge-not_invoice  { background: #f3f4f6; color: #374151; }
    .badge-unreadable   { background: #fee2e2; color: #991b1b; }

    /* Metric card tweak */
    div[data-testid="metric-container"] {
        background: #f9fafb;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 12px 16px;
    }
</style>
""", unsafe_allow_html=True)


#3. helper: build coloured badge HTML
def badge(status: str) -> str:
    label = status.replace("_", " ").title()
    return f'<span class="badge badge-{status}">{label}</span>'


#4. helper: convert rows list to CSV bytes for download
def rows_to_csv_bytes(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_HEADERS)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


#5. HEADER
st.title("🧾 AP Invoice Intake Helper")
st.markdown(
    "Upload vendor files to triage them automatically. "
    "Each file is classified, key fields are extracted, duplicates are flagged, "
    "and files are sorted into the right category."
)


#6. ocr status banner
if ocr_installed:
    st.success("OCR is ready — scanned PDFs and image files will be processed.", icon="✅")
else:
    st.warning(
        "OCR libraries (pytesseract / pdf2image) are not installed. "
        "Only text-layer PDFs will be processed. "
        "Install Tesseract + run `pip install pytesseract pdf2image` to enable OCR.",
        icon="⚠️",
    )
st.divider()


#7. SIDEBAR: settings
with st.sidebar:
    st.header("Settings")

    ocr_threshold = st.slider(
        "OCR confidence threshold",
        min_value=0,
        max_value=100,
        value=60,
        step=5,
        help="Files with average OCR confidence below this score are marked 'unclear' and sent to review.",
    )

    output_folder = st.text_input(
        "Output folder name",
        value="out",
        help="Sorted copies of files are placed here, alongside worklist.csv.",
    )
    st.divider()
    st.markdown("**How files are classified**")
    st.markdown("""
- 🟢 **OK** — clean invoice, all fields found  
- 🟡 **Review** — missing fields or low OCR confidence  
- 🔵 **Duplicate** — same vendor + invoice number seen before  
- ⚫ **Not invoice** — statement, credit note, delivery note, etc.  
- 🔴 **Unreadable** — corrupt, blank, or unsupported file  
    """)


#8. file uploader
st.subheader("Upload files")

uploaded = st.file_uploader(
    "Drop files here or click to browse",
    type=["pdf", "jpg", "jpeg", "png", "tiff", "tif", "bmp", "gif"],
    accept_multiple_files=True,
    label_visibility="collapsed",
)
if uploaded:
    st.caption(f"{len(uploaded)} file{'s' if len(uploaded) != 1 else ''} ready to process.")


#9. process button
process_clicked = st.button(
    "Process files",
    type="primary",
    disabled=not uploaded,
    use_container_width=False,
)

if process_clicked and uploaded:

    #override ocr threshold from sidebar
    import TASKSPEC
    TASKSPEC.ocr_confidence_threshold = ocr_threshold

    rows = []
    seen_keys: set[str] = set()

    #create a temp folder to save uploaded files to disk
    #process_file needs real file paths, not in-memory objects
    with tempfile.TemporaryDirectory() as tmp_input:
        input_path  = Path(tmp_input)
        output_path = Path(output_folder).resolve()
        out_dirs    = ensure_out_dirs(output_path)

        #save all uploaded files to temp folder
        for uf in uploaded:
            dest = input_path / uf.name
            dest.write_bytes(uf.read())

        #process each file with a live progress bar
        progress = st.progress(0, text="Starting…")
        total = len(uploaded)

        for i, uf in enumerate(uploaded):
            file_path = input_path / uf.name
            progress.progress(
                int((i / total) * 100),
                text=f"Processing {uf.name}…",
            )

            try:
                row = process_file(file_path, seen_keys, out_dirs)
            except Exception as e:
                row = {col: "" for col in CSV_HEADERS}
                row["file"]   = uf.name
                row["status"] = "unreadable"
                row["notes"]  = f"Unexpected error: {e}"
                shutil.copy2(file_path, out_dirs["unreadable"] / uf.name)

            rows.append(row)

        progress.progress(100, text="Done!")

    #save results into session state so they persist after rerun
    st.session_state["rows"]       = rows
    st.session_state["csv_bytes"]  = rows_to_csv_bytes(rows)


#10. results (shown from session state so they survive re-renders)
if "rows" in st.session_state:
    rows = st.session_state["rows"]
    st.divider()

    #summary
    st.subheader("Summary")
    counts = Counter(r["status"] for r in rows)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("✅ OK",          counts.get("ok", 0))
    c2.metric("🟡 Review",      counts.get("review", 0))
    c3.metric("🔵 Duplicate",   counts.get("duplicate", 0))
    c4.metric("⚫ Not invoice",  counts.get("not_invoice", 0))
    c5.metric("🔴 Unreadable",  counts.get("unreadable", 0))

    st.divider()

    #filter & results table
    col_left, col_right = st.columns([3, 1])
    with col_left:
        st.subheader("Results")
    with col_right:
        st.download_button(
            label="⬇ Download worklist.csv",
            data=st.session_state["csv_bytes"],
            file_name="worklist.csv",
            mime="text/csv",
            use_container_width=True,
        )

    #status filter
    all_statuses = ["all", "ok", "review", "duplicate", "not_invoice", "unreadable"]
    chosen = st.radio(
        "Filter by status",
        options=all_statuses,
        format_func=lambda s: s.replace("_", " ").title() if s != "all" else "All",
        horizontal=True,
        label_visibility="collapsed",
    )

    filtered = rows if chosen == "all" else [r for r in rows if r["status"] == chosen]

    if not filtered:
        st.info("No files in this category.")
    else:
        #build an html table with coloured status badges
        header = """
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="background:#f9fafb;border-bottom:1px solid #e5e7eb">
              <th style="padding:10px 14px;text-align:left;width:22%">File</th>
              <th style="padding:10px 14px;text-align:left;width:12%">Doc type</th>
              <th style="padding:10px 14px;text-align:left;width:18%">Vendor</th>
              <th style="padding:10px 14px;text-align:left;width:13%">Invoice no.</th>
              <th style="padding:10px 14px;text-align:left;width:10%">Amount</th>
              <th style="padding:10px 14px;text-align:left;width:10%">Status</th>
              <th style="padding:10px 14px;text-align:left;width:15%">Notes</th>
            </tr>
          </thead>
          <tbody>
        """

        body = ""
        for i, r in enumerate(filtered):
            bg = "#ffffff" if i % 2 == 0 else "#f9fafb"
            body += f"""
            <tr style="background:{bg};border-bottom:1px solid #f3f4f6">
              <td style="padding:10px 14px;max-width:0;overflow:hidden;
                         text-overflow:ellipsis;white-space:nowrap"
                  title="{r['file']}">{r['file']}</td>
              <td style="padding:10px 14px">{r['doc_type'] or '—'}</td>
              <td style="padding:10px 14px;max-width:0;overflow:hidden;
                         text-overflow:ellipsis;white-space:nowrap"
                  title="{r['vendor']}">{r['vendor'] or '—'}</td>
              <td style="padding:10px 14px">{r['invoice_number'] or '—'}</td>
              <td style="padding:10px 14px">{r['amount'] or '—'}</td>
              <td style="padding:10px 14px">{badge(r['status'])}</td>
              <td style="padding:10px 14px;color:#6b7280;font-size:12px;
                         max-width:0;overflow:hidden;text-overflow:ellipsis;
                         white-space:nowrap"
                  title="{r['notes']}">{r['notes'] or '—'}</td>
            </tr>
            """

        footer = "</tbody></table>"
        st.markdown(header + body + footer, unsafe_allow_html=True)

    #individual file expander (shows all fields for that row)
    st.divider()
    st.subheader("File details")
    st.caption("Expand any file to see all extracted fields.")

    for r in filtered:
        status_icon = {
            "ok": "✅", "review": "🟡", "duplicate": "🔵",
            "not_invoice": "⚫", "unreadable": "🔴",
        }.get(r["status"], "❓")

        with st.expander(f"{status_icon}  {r['file']}"):
            d1, d2, d3 = st.columns(3)
            d1.markdown(f"**Status:** {r['status'].replace('_',' ').title()}")
            d1.markdown(f"**Doc type:** {r['doc_type'] or '—'}")
            d1.markdown(f"**Legibility:** {r['legibility'] or '—'}")
            d2.markdown(f"**Vendor:** {r['vendor'] or '—'}")
            d2.markdown(f"**Invoice no.:** {r['invoice_number'] or '—'}")
            d2.markdown(f"**Invoice date:** {r['invoice_date'] or '—'}")
            d3.markdown(f"**Amount:** {r['amount'] or '—'}")
            d3.markdown(f"**OCR confidence:** {r['ocr_confidence'] or '—'}")
            if r["notes"]:
                st.info(r["notes"], icon="ℹ️")