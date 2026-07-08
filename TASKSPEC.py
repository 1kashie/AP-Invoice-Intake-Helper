"""AP INVOICE INTAKE HELPER (FIXED)"""
import csv
import shutil                                                                           
import re                                                                               
import pdfplumber                                                                       
from PIL import Image                                                                   
from pathlib import Path

try:                                                                                    
    import pytesseract
    from pdf2image import convert_from_path
    ocr_installed = True
except ImportError:
    ocr_installed = False

output_folders = ['ok', 'review', 'duplicate', 'not_invoice', 'unreadable']
simple_keywords = {
    "credit_note":    ["credit note", "credit memo", "cn-", "credit #", "credit no"],
    "statement":      ["statement of account", "account statement", "remittance"],
    "invoice":        ["invoice", "inv #", "inv no", "bill to", "due date"],
    "delivery_note":  ["delivery note", "packing slip", "delivery #", "delivery no"],
}

vendor_patterns = [
    r"(?:from|vendor|supplier|billed?\s*by)[:\s]+([A-Z][A-Za-z0-9 &.,'\-]{2,50})",
    r"(?:vendor|supplier)\s*(?:bill\s*to)?\s*\n([A-Z][A-Za-z0-9 &.,'\-]{2,50})",
    r"^([A-Z][A-Za-z0-9 &.,'\-]{2,50}(?:\s+LLC|\s+Ltd\.?|\s+Inc\.?|\s+Corp\.?))",
]

inv_no_patterns = [
    r"invoice\s*(?:no\.?|number|#)\s*[:\s]\s*([A-Za-z0-9\-\/]{3,30})",
    r"inv\.?\s*(?:no\.?|#)\s*[:\s]\s*([A-Za-z0-9\-\/]{3,30})",
    r"invoice\s*#\s*\[([A-Za-z0-9\-\/]{3,30})\]",
    r"invoice\s*number\s+.*?(INV[-\/]?\d{3,10})",
    r"\b(INV[-\/]\d{3,10})\b",
    r"(?:^|\s)([A-Z]{2,4}[-\/]?\d{4,10})\b",
]

date_patterns = [
    r"invoice\s*date\s*(?:\([^)]*\))?\s*(\d{4}[-\/]\d{2}[-\/]\d{2})",
    r"invoice\s*date\s+([A-Z][a-z]+ \d{1,2},?\s*\d{4})",
    r"(?:invoice\s*date|date)[:\s]+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
    r"invoice\s*date\s*\n(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
    r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*,?\s+\d{4})",
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})",
    r"\b(\d{4}[-\/]\d{2}[-\/]\d{2})\b",
    r"\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})\b",
]

amt_patterns = [
    r"(?:total\s*due|total|amount\s*due|grand\s*total|balance\s*due)\s*[$£€]?\s*([\d,]+(?:\.\d{2})?)",
    r"[$£€]\s*([\d,]+\.\d{2})\s*$",
    r"TOTAL\s+[$£€]?\s*([\d,]+(?:\.\d{2})?)",
]
 
ocr_confidence_threshold = 60

def ensure_out_dirs(base: Path) -> dict[str, Path]:
    dirs = {}
    for folder in output_folders:
        out_dir = base / folder
        out_dir.mkdir(parents=True, exist_ok=True)
        dirs[folder] = out_dir
    return dirs

def copy_file(src: Path, dest: Path) -> None:
    dest = dest / src.name
    ctr=1
    while dest.exists():
        dest = dest.with_name(f"{src.stem}_{ctr}{src.suffix}")
        ctr += 1
    shutil.copy2(src, dest)

def extract_first(text: str, patterns: list) -> str:
    for p in patterns:
        match = re.search(p, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return ""

def extract_pdf_text(path: Path) -> str:
    text = ""
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
    except Exception as e:
        print(f"Error reading PDF {path}: {e}")
    return text

def ocr_pdf(path: Path) -> tuple[str, float]:
    if not ocr_installed:
        print("OCR libraries not installed. Skipping OCR.")
        return "", 0.0
    try:
        images = convert_from_path(path, dpi=200) # type: ignore
        return _ocr_image(images)  # Delegate to helper to get accurate confidence metrics
    except Exception as e:
        print(f"Error performing OCR on PDF {path}: {e}")
        return "", 0.0

def ocr_image(path: Path) -> tuple[str, float]:
    if not ocr_installed:
        print("OCR libraries not installed. Skipping OCR.")
        return "", 0.0
    try:
        img = Image.open(path)
        return _ocr_image([img])
    except Exception as e:
        print(f"Error performing OCR on image {path}: {e}")
        return "", 0.0
    
def _ocr_image(images: list) -> tuple[str, float]:
    alltext: list[str] = []
    conf_scores: list[float] = []
    for img in images:
        img = img.convert("RGB")
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT) # type: ignore
        page_t = []
        for i, word in enumerate(data['text']):
            conf = data['conf'][i]
            if isinstance(conf, (int, float)) and conf >= 0 and word.strip():
                page_t.append(word)
                conf_scores.append(float(conf))
        alltext.append(" ".join(page_t))
    text = "\n".join(alltext)
    avg_conf = sum(conf_scores) / len(conf_scores) if conf_scores else 0
    return text, avg_conf

def extract_invoice_data(text: str) -> dict:
    return {
        "vendor": extract_first(text, vendor_patterns),
        "invoice_number": extract_first(text, inv_no_patterns),
        "invoice_date": extract_first(text, date_patterns),
        "amount": extract_first(text, amt_patterns),
    }

def classify_doc(text: str) -> str:
    text_lower = text.lower()
    for doc_type, keywords in simple_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            return doc_type
    return "unknown"

img_extensions = ['.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.gif']
pdf_extensions = ['.pdf']

def process_file(path: Path, seen_keys: set[str], out_dirs: dict[str, Path]) -> dict:
    row = { 
        "file"              : path.name,
        "doc_type"          : "",
        "legibility"        : "",
        "ocr_confidence"    : "",
        "vendor"            : "",
        "invoice_number"    : "",
        "invoice_date"      : "",
        "amount"            : "",
        "status"            : "",
        "notes"             : ""
    }
    suffix = path.suffix.lower()

    # 1. Structural/Corrupt Checks
    if path.stat().st_size == 0:
        row["status"] = "unreadable"
        row["legibility"] = "unreadable"
        row["notes"] = "File is empty."
        copy_file(path, out_dirs["unreadable"])
        return row
        
    if suffix not in (img_extensions + pdf_extensions):
        row["status"] = "unreadable"
        row["legibility"] = "unreadable"
        row["notes"] = "Unsupported file type."
        copy_file(path, out_dirs["unreadable"])
        return row

    text = ""
    ocr_conf = None

    # 2. Text Extraction & Ingestion Gate
    if suffix in pdf_extensions:
        text = extract_pdf_text(path)
        if text.strip():
            row["legibility"] = "clear"
        else:
            if ocr_installed:
                text, ocr_conf = ocr_pdf(path)
                row["ocr_confidence"] = f"{ocr_conf:.0f}"
            else:
                row["notes"] = "OCR not installed, cannot process scanned PDF."
    elif suffix in img_extensions:
        if ocr_installed:
            text, ocr_conf = ocr_image(path)
            row["ocr_confidence"] = f"{ocr_conf:.0f}"
        else:
            row["notes"] = "OCR not installed, cannot process image file."
        
    # Evaluate OCR results if OCR was invoked
    if ocr_conf is not None:
        word_count = len(text.split())
        if ocr_conf >= ocr_confidence_threshold and word_count >= 10:
            row["legibility"] = "clear"
        elif ocr_conf > 0:
            row["legibility"] = "unclear"
        else:
            row["legibility"] = "unreadable"

    # 3. Handling Unreadable/Unclear Text Routers
    if not text.strip() or row["legibility"] == "unreadable":
        row["legibility"] = "unreadable"
        row["status"] = "unreadable"
        row["notes"] = "No readable text could be extracted."
        copy_file(path, out_dirs["unreadable"])
        return row

    if row["legibility"] == "unclear":
        row["status"] = "review"
        row["notes"] = "Scanned document text is blurry or dark. Needs human verification."
        copy_file(path, out_dirs["review"])
        return row
        
    # 4. Document Classification Engine
    doc_type = classify_doc(text)
    row["doc_type"] = doc_type
    if doc_type != "invoice":
        row["status"] = "not_invoice"
        row["notes"] = f"Document recognized as a {doc_type.replace('_', ' ')} instead of an invoice."
        copy_file(path, out_dirs["not_invoice"])
        return row

    # 5. Metadata Processing & Regex Extraction
    fields = extract_invoice_data(text)
    row.update(fields)
    
    vendor = fields["vendor"].lower().strip()
    inv_no = fields["invoice_number"].lower().strip()
    dedup_key = f"{vendor}|{inv_no}" if vendor and inv_no else ""

    # Check Duplication
    if dedup_key and dedup_key in seen_keys:
        row["status"] = "duplicate"
        row["notes"] = "Duplicate document detected (Same supplier and invoice sequence match)."
        copy_file(path, out_dirs["duplicate"])
        return row
        
    if dedup_key:
        seen_keys.add(dedup_key)

    # Missing Field Verification (Accounting Plain Language)
    missing = []
    if not fields["vendor"]: missing.append("Supplier Name")
    if not fields["invoice_number"]: missing.append("Invoice Number")
    if not fields["invoice_date"]: missing.append("Invoice Date")
    if not fields["amount"]: missing.append("Total Amount")
        
    if missing:
        row["status"] = "review"
        row["notes"] = f"Incomplete details. Missing: {', '.join(missing)}."       
        copy_file(path, out_dirs["review"])
        return row
    else:
        row["status"] = "ok"
        row["notes"] = "All checks passed successfully."
        copy_file(path, out_dirs["ok"])
        return row
        
CSV_HEADERS = ["file", "doc_type", "legibility", "ocr_confidence", "vendor", "invoice_number", "invoice_date", "amount", "status", "notes"]
        
def run(input_dir: Path, output_dir: Path) -> None:
    input_path = Path(input_dir).resolve()
    output_path = Path(output_dir).resolve()
    if not input_path.exists():
        raise SystemExit(f"Input directory {input_path} does not exist.")
    out_dirs = ensure_out_dirs(output_path)
    
    all_files = [f for f in sorted(input_path.iterdir()) if f.is_file()]
    if not all_files:
        print(f"No files found in {input_path}.")
        return
            
    seen_keys = set()
    rows: list[dict] = []
    worklist_path = output_path / "worklist.csv"
    
    for file_path in all_files:
        print(f"Processing {file_path.name}...", end=" ", flush=True)
        try:
            row = process_file(file_path, seen_keys, out_dirs)
            rows.append(row)
            print(f"-> {row['status']}")
        except Exception as e:
            row = {col: "" for col in CSV_HEADERS}
            row["file"] = file_path.name
            row["status"] = "unreadable"
            row["notes"] = f"System Error processing file: {e}"
            shutil.copy2(file_path, out_dirs["unreadable"] / file_path.name)
            rows.append(row)
            print(f"-> {row['status']}")

    with open(worklist_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    
    print("\n-------- Processing complete. Summary:")
    from collections import Counter
    counts = Counter(r["status"] for r in rows)
    for status in ["ok", "review", "duplicate", "not_invoice", "unreadable"]:
        print(f"{status:15s}: {counts.get(status, 0)}")

if __name__ == "__main__":
    worklist_path = Path("sample_invoices")
    output_path = Path("out")
    run(worklist_path, output_path)