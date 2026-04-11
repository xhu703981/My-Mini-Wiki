import pathlib
import fitz  # pymupdf

RAW_DIR = pathlib.Path(__file__).parent.parent / "raw"

def split_pdf(filename, start_page, end_page, output_name=None):
    """
    filename: raw/目录下的PDF文件名
    start_page: 起始页（从1开始）
    end_page: 结束页（包含）
    output_name: 输出文件名，不填则自动命名
    """
    input_path = RAW_DIR / filename
    if not input_path.exists():
        print(f"文件不存在: {input_path}")
        return

    doc = fitz.open(input_path)
    total_pages = len(doc)
    print(f"文件：{filename}，共 {total_pages} 页")

    # 转成0-indexed
    start = start_page - 1
    end = end_page  # fitz的select是exclusive end

    if start < 0 or end > total_pages:
        print(f"页码超出范围，该PDF共 {total_pages} 页")
        return

    # 提取指定页
    new_doc = fitz.open()
    new_doc.insert_pdf(doc, from_page=start, to_page=end - 1)

    # 输出文件名
    if not output_name:
        base = pathlib.Path(filename).stem
        output_name = f"{base}_p{start_page}-{end_page}.pdf"

    if not output_name.endswith(".pdf"):
        output_name += ".pdf"
        output_path = RAW_DIR / output_name
    new_doc.save(output_path)
    print(f"已保存：{output_name}（{end_page - start_page + 1} 页）")


if __name__ == "__main__":
    print("PDF分割工具")
    print(f"raw/ 目录下的PDF文件：")
    
    pdfs = list(RAW_DIR.glob("*.pdf"))
    for i, p in enumerate(pdfs):
        doc = fitz.open(p)
        print(f"  [{i}] {p.name}（{len(doc)} 页）")

    print()
    filename = input("输入文件名（含.pdf）：").strip()
    start = int(input("起始页：").strip())
    end = int(input("结束页：").strip())
    name = input("输出文件名（留空自动命名）：").strip()

    split_pdf(filename, start, end, name if name else None)