import pathlib
import fitz  # pymupdf

RAW_DIR = pathlib.Path(__file__).parent.parent / "raw"

def split_pdf(filename, start_page, end_page, output_name=None):
    input_path = RAW_DIR / filename
    if not input_path.exists():
        print(f"File not found: {input_path}")
        return
    doc = fitz.open(input_path)
    total_pages = len(doc)
    print(f"File: {filename}, {total_pages} pages total")
    start = start_page - 1
    end = end_page  
    if start < 0 or end > total_pages:
        print(f"Page range out of bounds, PDF has {total_pages} pages")
        return
    new_doc = fitz.open()
    new_doc.insert_pdf(doc, from_page=start, to_page=end - 1)
    if not output_name:
        base = pathlib.Path(filename).stem
        output_name = f"{base}_p{start_page}-{end_page}.pdf"
    if not output_name.endswith(".pdf"):
        output_name += ".pdf"
    output_path = RAW_DIR / output_name
    new_doc.save(output_path)
    print(f"Saved: {output_name} ({end_page - start_page + 1} pages)")

if __name__ == "__main__":
    print("PDF Splitter")
    print("PDFs in raw/:")
    pdfs = list(RAW_DIR.glob("*.pdf"))
    for i, p in enumerate(pdfs):
        doc = fitz.open(p)
        print(f"  [{i}] {p.name} ({len(doc)} pages)")
    print()
    filename = input("Filename (with .pdf): ").strip()
    start = int(input("Start page: ").strip())
    end = int(input("End page: ").strip())
    name = input("Output filename (leave blank for auto): ").strip()
    split_pdf(filename, start, end, name if name else None)