import pathlib
import base64
import json
from google import genai
from google.genai import types
import fitz
from dotenv import load_dotenv
import os 

# 配置
load_dotenv()
API_KEY = os.getenv("GEMIMI_API_KEY")
RAW_DIR = pathlib.Path(__file__).parent.parent / "raw"
WIKI_DIR = pathlib.Path(__file__).parent.parent / "wiki"
PROCESSED_FILE = pathlib.Path(__file__).parent.parent / "processed.json"

#client
client = genai.Client(api_key=API_KEY)

#Methods
def load_processed():
    if PROCESSED_FILE.exists():
        return json.loads(PROCESSED_FILE.read_text(encoding="utf-8"))
    return {}

def save_processed(processed):
    PROCESSED_FILE.write_text(json.dumps(processed, indent=2, ensure_ascii=False), encoding="utf-8")

def get_new_files(processed):
    text_extensions = ["*.md", "*.txt", "*.py", "*.js", "*.ts", "*.cpp",
                       "*.c", "*.java", "*.r", "*.m", "*.ipynb"]
    image_extensions = ["*.png", "*.jpg", "*.jpeg", "*.webp"]
    all_files = []
    for ext in text_extensions + image_extensions + ["*.pdf"]:
        all_files += list(RAW_DIR.glob(f"**/{ext}"))
    new_files = []
    for f in all_files:
        mtime = str(f.stat().st_mtime)
        if f.name not in processed or processed[f.name] != mtime:
            new_files.append(f)
    return new_files

def read_files(files):
    text_extensions = {".md", ".txt", ".py", ".js", ".ts", ".cpp",
                       ".c", ".java", ".r", ".m", ".ipynb"}
    image_extensions = {".png", ".jpg", ".jpeg", ".webp"}
    combined_text = ""
    images = []
    for f in files:
        suffix = f.suffix.lower()
        if suffix in text_extensions:
            try:
                combined_text += f"\n\n--- FILE: {f.name} ---\n" + f.read_text(encoding="utf-8")
            except Exception as e:
                print(f"  Skipped: {f.name} — {e}")
        elif suffix == ".pdf":
            print(f"Reading PDF: {f.name}")
            doc = fitz.open(f)
            text = ""
            for page in doc:
                text += page.get_text()
            combined_text += f"\n\n--- FILE: {f.name} ---\n" + text
        elif suffix in image_extensions:
            print(f"Reading image: {f.name}")
            with open(f, "rb") as img_file:
                b64 = base64.b64encode(img_file.read()).decode()
                mime = "image/jpeg" if suffix in [".jpg", ".jpeg"] else f"image/{suffix[1:]}"
                images.append({"name": f.name, "data": b64, "mime": mime})
    return combined_text, images

def read_existing_wiki():
    # 排除_index.md，避免污染其他文章
    files = [f for f in WIKI_DIR.glob("**/*.md") if f.name != "_index.md"]
    if not files:
        return ""
    combined = ""
    for f in files:
        combined += f"\n\n--- WIKI FILE: {f.name} ---\n" + f.read_text(encoding="utf-8")
    return combined

def strip_codeblock(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    if text.endswith("```"):
        text = text.rsplit("\n", 1)[0]
    return text.strip()

def compile_wiki(text_content, images, existing_wiki):
    parts = []
    mode = "Incremental update" if existing_wiki else "Full generation"
    print(f"Mode: {mode}")
    existing_section = f"""
Existing wiki content (preserve and expand, do not delete existing content):
{existing_wiki}
""" if existing_wiki else "(This is the first time generating the wiki.)"

    prompt = f"""
You are a knowledge base compiler. Based on the new materials provided, {'update and expand the existing wiki' if existing_wiki else 'generate a wiki knowledge base'}.

Requirements:
1. Extract all core concepts from new materials, write one article per concept
2. Each article must include: concept explanation, key takeaways, and connections to other concepts
3. For code files, extract algorithm logic and implementation ideas
4. For images, extract the knowledge and concepts shown
5. For techinical document, extract the key concepts,implementation ideas to make sure what's output is a contracted document
6. Use [[concept name]] syntax for bidirectional links between articles (Obsidian format)
7. If new concepts relate to existing wiki articles, add "Related Concepts" links at the end of those articles
8. Output format: separate each file with === FILE: filename.md === on its own line
9. Only output new or modified files, do not repeat unchanged files
10. Write all articles in English, including file names and titles
11. Do NOT wrap output in markdown code blocks
12. When creating [[links]], only link to concepts that you are ALSO creating an article for in this output. Do not create links to concepts that don't have a corresponding article.

{existing_section}

New materials:
{text_content}

Number of new images: {len(images)}
"""
    parts.append(prompt)
    for img in images:
        parts.append(f"\nImage file: {img['name']}")
        parts.append(types.Part.from_bytes(
            data=base64.b64decode(img["data"]),
            mime_type=img["mime"]
        ))
    print("Calling Gemini to compile wiki...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=parts
    )
    return response.text

def save_wiki(text):
    WIKI_DIR.mkdir(exist_ok=True)
    text = strip_codeblock(text)
    sections = text.split("=== FILE:")
    saved = 0
    for section in sections:
        section = section.strip()
        if not section:
            continue
        lines = section.split("\n", 1)
        filename = lines[0].strip().rstrip("===").strip()
# 替换Windows文件名非法字符
        filename = filename.replace("\\", "-").replace("/", "-").replace(":", "-").replace("*", "-").replace("?", "-").replace('"', "-").replace("<", "-").replace(">", "-").replace("|", "-")
        content = lines[1].strip() if len(lines) > 1 else ""
        content = strip_codeblock(content)
        if filename.endswith(".md"):
            filepath = WIKI_DIR / filename
            filepath.write_text(content, encoding="utf-8")
            print(f"Saved: {filename}")
            saved += 1
    print(f"\nDone! {saved} files updated.")

def rebuild_index():
    files = [f for f in WIKI_DIR.glob("**/*.md") if f.name != "_index.md"]
    if not files:
        return
    prompt = "Based on the following wiki articles, generate a _index.md master index.\n\nRequirements:\n1. Every article name MUST use Obsidian link format: [[article name]] — one sentence summary\n2. Group by topic with ## subheadings\n3. Keep summaries concise, under 15 words\n4. Write everything in English\n5. Do NOT write plain text article names, ALWAYS use [[]] format\n6. Do NOT wrap output in markdown code blocks\n\nArticle summaries:\n"
    for f in sorted(files):
        content = f.read_text(encoding="utf-8")[:200]
        prompt += f"\n\n{f.name}:\n{content}"
    print("Rebuilding _index.md...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    index_path = WIKI_DIR / "_index.md"
    index_content = strip_codeblock(response.text)
    index_path.write_text(index_content, encoding="utf-8")
    print("_index.md updated.")

if __name__ == "__main__":
    processed = load_processed()
    new_files = get_new_files(processed)
    if not new_files:
        print("No new files. Wiki is up to date.")
    else:
        print(f"Found {len(new_files)} new/modified files:")
        for f in new_files:
            print(f"  {f.name}")
        print()
        text_content, images = read_files(new_files)
        existing_wiki = read_existing_wiki()
        wiki_text = compile_wiki(text_content, images, existing_wiki)
        save_wiki(wiki_text)
        rebuild_index()
        for f in new_files:
            processed[f.name] = str(f.stat().st_mtime)
        save_processed(processed)
        print("processed.json updated.")