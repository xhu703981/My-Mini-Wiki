import pathlib
import base64
import json
from google import genai
from google.genai import types
import fitz
from dotenv import load_dotenv
import os 
import build_index

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

def strip_codeblock(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    if text.endswith("```"):
        text = text.rsplit("\n", 1)[0]
    return text.strip()

def compile_wiki(text_content, images):
    parts = []
    prompt = f"""
You are a knowledge base compiler. Based on the new materials provided, update and expand the existing wiki.

Requirements:
1. Extract all core concepts from new materials, write one article per concept
2. Each article must include: concept explanation, key takeaways, and connections to other concepts
3. For code files, extract algorithm logic and implementation ideas
4. For images, extract the knowledge and concepts shown
5. For techinical document, extract the key concepts,implementation ideas to make sure what's output is a contracted document
6. Use [[concept name]] syntax for bidirectional links between articles (Obsidian format)
8. Output format: separate each file with === FILE: filename.md === on its own line
10. Write all articles in English, including file names and titles
11. Do NOT wrap output in markdown code blocks

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
    files_to_be_index=[]
    for section in sections:
        section = section.strip()
        if not section:
            continue
        lines = section.split("\n", 1)
        filename = lines[0].strip().rstrip("===").strip()
        filename = filename.replace("\\", "-").replace("/", "-").replace(":", "-").replace("*", "-").replace("?", "-").replace('"', "-").replace("<", "-").replace(">", "-").replace("|", "-")
        content = lines[1].strip() if len(lines) > 1 else ""
        content = strip_codeblock(content)
        if filename.endswith(".md"):
            filepath = WIKI_DIR / filename
            filepath.write_text(content, encoding="utf-8")
            files_to_be_index.append(filepath)
            print(f"Saved: {filename}")
            saved += 1
    print(f"\nDone! {saved} files updated.")
    return files_to_be_index

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
        wiki_text = compile_wiki(text_content, images)
        file_tobe_index = save_wiki(wiki_text)
        for f in new_files:
            processed[f.name] = str(f.stat().st_mtime)
        save_processed(processed)
        print("processed.json updated.")
        build_index.create_index(build_index.client, force=False)
        build_index.index_wiki(build_index.client,files=file_tobe_index)
    