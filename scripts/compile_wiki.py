import pathlib
import base64
import json
import time
from google import genai
from google.genai import types
import fitz
from dotenv import load_dotenv
import os 
import build_index

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
RAW_DIR = pathlib.Path(__file__).parent.parent / "raw"
WIKI_DIR = pathlib.Path(__file__).parent.parent / "wiki"
PROCESSED_FILE = pathlib.Path(__file__).parent.parent / "processed.json"
text_extensions = [".md", ".txt", ".py", ".js", ".cpp",".c", ".java",".ipynb"]
image_extensions = [".png", ".jpg"]
pdf_extensions=[".pdf"]
client = genai.Client(api_key=API_KEY)
token_limit=700000

def load_processed():
    if PROCESSED_FILE.exists():
        return set(json.loads(PROCESSED_FILE.read_text(encoding="utf-8")))
    return set()

def save_processed(processed):
    PROCESSED_FILE.write_text(json.dumps(list(processed), indent=2, ensure_ascii=False), encoding="utf-8")

def get_new_files(processed):
    all_extensions=set(text_extensions+image_extensions+pdf_extensions)
    new_files=[]
    for file in RAW_DIR.glob("**/*"):
        if file.suffix in all_extensions:
            if file.name not in processed:
                new_files.append(file)
    return new_files

def read_files(files):
    current_text = ""
    current_images = []
    current_files = []
    batches=[]
    current_token=0
    for file in files:
        token_count=0
        new_text=""
        new_image=None
        if file.suffix in text_extensions:
            new_text=file.read_text(encoding="utf-8")
            token_count = len(new_text) // 4

        if file.suffix in pdf_extensions:
            new_text=""
            doc=fitz.open(file)
            for page in doc:
                new_text+=page.get_text()
            token_count = len(new_text) // 4

        if file.suffix in image_extensions:
            with open(file,"rb") as image_file:
                b64=base64.b64encode(image_file.read()).decode()
            if file.suffix==".jpg":
                mime="image/jpeg"
            if file.suffix==".png":
                mime="image/png"
            new_image={"data":b64,"mime":mime}
            token_count=1000

        if token_count+current_token<token_limit:
            if file.suffix in text_extensions or file.suffix in pdf_extensions:
                current_text+=new_text
            elif file.suffix in image_extensions:
                current_images.append(new_image)
            current_files.append(file)
            current_token+=token_count

        else:
            batches.append((current_text, current_images, current_files))
            current_text = new_text if file.suffix not in image_extensions else ""
            current_images = [new_image] if file.suffix in image_extensions else []
            current_files = [file]
            current_token=token_count

    batches.append((current_text, current_images, current_files))
    return batches

def compile_wiki(combined_text, images):
    parts=[]
    prompt = f"""
You are a knowledge base compiler. Extract concepts from the provided materials and write wiki articles.

WHAT TO WRITE:
- One article per distinct concept, principle, or reusable idea
- For code files: extract the underlying algorithm logic and design decisions, not the syntax
- For technical documents: extract principles and mental models, not step-by-step procedures
- For images: extract the knowledge and concepts shown

DO NOT WRITE ARTICLES FOR:
- Specific implementation details or API parameters (e.g. "how to configure X in version Y")
- Anything that can be fully expressed in one sentence
- Content that only makes sense within the specific context of the source material
- Procedural steps that don't generalize beyond one tool or system

ARTICLE STRUCTURE (use this exact format for every article):
## [Concept Name]
[2-3 paragraph explanation that stands on its own — written so that you can understand it months later with no memory of the source material]

## Key Takeaways
- [Actionable insight, not a summary. What should you DO or THINK differently because of this?]

## Connections
- [[Related Concept]]: [One sentence explaining WHY these two concepts are related]

LINKING RULES:
- Use [[concept name]] syntax (Obsidian format) for all links
- Only link concepts that have a meaningful relationship worth explaining
- Links should appear naturally in the text, not just in the Connections section

OUTPUT FORMAT:
- Separate each article with === FILE: filename.md === on its own line
- File names in English, lowercase with hyphens (e.g. vector-search.md)
- Do NOT wrap output in markdown code blocks

New materials:
{combined_text}
"""
    parts.append(prompt)
    for image in images:
        parts.append(types.Part.from_bytes(data=base64.b64decode(image["data"]), mime_type=image["mime"]))
    for attempt in range(3):
        try:
            response=client.models.generate_content(model="gemini-2.5-flash",contents=parts)
            return response.text
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(30)
    raise Exception("All retries failed")

def strip_codeblock(text):  #sometimes gemini does not listen to me 
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    if text.endswith("```"):
        text = text.rsplit("\n", 1)[0]
    return text.strip() 

def save_wiki(text):
    WIKI_DIR.mkdir(exist_ok=True)
    text = strip_codeblock(text)
    sections = text.split("=== FILE:")
    files_to_be_index=[]
    for section in sections:
        section = section.strip()
        if not section: continue
        lines = section.split("\n", 1)
        filename = lines[0].strip().rstrip("===").strip()
        filename = filename.replace("\\", "-").replace("/", "-").replace(":", "-").replace("*", "-").replace("?", "-").replace('"', "-").replace("<", "-").replace(">", "-").replace("|", "-") # gosh... windows ......
        content = lines[1].strip() if len(lines) > 1 else ""
        content = strip_codeblock(content)
        if filename.endswith(".md"):
            filepath = WIKI_DIR / filename
            filepath.write_text(content, encoding="utf-8")
            files_to_be_index.append(filepath)
    return files_to_be_index

if __name__ == "__main__":
    processed = load_processed()
    new_files = get_new_files(processed)
    if not new_files:
        print("No new files")
    else:
        for f in new_files:
            print(f"  {f.name}")
        batches = read_files(new_files)
        file_tobe_index = []
        for i, (text, images, batch_files) in enumerate(batches):
            print(f"\nBatch {i+1}/{len(batches)}: {[f.name for f in batch_files]}")
            wiki_text = compile_wiki(text, images)
            file_tobe_index += save_wiki(wiki_text)
            for f in batch_files:
                processed.add(f.name)
            save_processed(processed)
        build_index.create_index(build_index.client, force=True)
        build_index.index_wiki(build_index.client,files=file_tobe_index)
    