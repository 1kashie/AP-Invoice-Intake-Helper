# AP-Invoice-Intake-Helper
From a messy pile of files to a clean, sorted worklist automatically. This tool handles the first-pass sorting that AP teams using Python, OCR, and smart classification rules to get invoices ready for processing with zero manual effort where each file is read, identified, and evaluated for legibility and content type.

HOW TO RUN IT?
1. First INSTALL these dependancies in windows terminal in one shot:
   pip install pdfplumber pypdf pillow pytesseract pdf2image
   and VERIFY them python -c "import pdfplumber, pypdf, pytesseract; from PIL import Image; from     pdf2image import convert_from_path; print('All packages OK')"
   tesseract --version pdftoppm -v
3. cd "/Users/murali/Downloads/TASK SPEC AP INVOICE INTAKE HELPER"    (COPY File Location)
4. python3 -m streamlit run app.py (FOR MACOS),
   streamlit run app.py (FOR WINDOWS)

HOW ARE THE FILES CLASSIFIED:
🟢 OK — clean invoice, all fields found
🟡 Review — missing fields or low OCR confidence
🔵 Duplicate — same vendor + invoice number seen before
⚫ Not invoice — statement, credit note, delivery note, etc.
🔴 Unreadable — corrupt, blank, or unsupported file

WHY IS THE OCR THRESHOLD SET UP AT 60 IN DEFAULT?
60 sits at the boundary between "risky" and "generally readable" — which is why it's a reasonable first guess.
Score 0–40   → Almost certainly garbage. Blurry, rotated,
               or heavily degraded scan. Nobody should trust this.

Score 40–60  → Risky zone. Some words readable but too many
               errors to trust extracted fields like invoice
               numbers or amounts.

Score 60–80  → Generally readable. Most words correct.
               Occasional errors but fields are likely right.

Score 80–100 → Very clean scan. High confidence. Almost as
               good as a text-layer PDF.
