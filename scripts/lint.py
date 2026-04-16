import pathlib
import re
from google import genai
from dotenv import load_dotenv
import os 
import build_index

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
WIKI_DIR = pathlib.Path(__file__).parent.parent / "wiki"
client = genai.Client(api_key=API_KEY)
token_limit=700000

def read_articles():
    files = [f for f in WIKI_DIR.glob("*.md") if not f.name.startswith("_")]
    combined_text=""
    current_token=0
    batches=[]
    for file in files:
        token_count=0
        current_text=f"=== ARTICLE: {file.name} ===\n" +file.read_text(encoding="utf-8")
        token_count=len(current_text)//4
        if token_count+current_token<token_limit:
            combined_text+=current_text
            current_token+=token_count
        else:
            batches.append(combined_text)
            combined_text=current_text
            current_token=len(current_text)//4
    batches.append(combined_text)
    return batches

def get_command(text):
    prompt = f"""
You are a knowledge base editor. Analyze the following wiki articles and improve the knowledge base.

Perform these operations where needed:

MERGE: Combine articles that cover the same concept or have significant overlap.
DELETE: Remove articles that are too specific, procedural, or not reusable knowledge.
UPDATE: Rewrite articles that are incomplete, unclear, or need better connections.
LINK: Fix or add [[concept]] links between related articles.

OUTPUT FORMAT — output ONLY operation blocks, no commentary:

For MERGE:
=== MERGE: result-filename.md ===
[full content of merged article]

For DELETE:
=== DELETE: filename.md ===

For UPDATE:
=== UPDATE: filename.md ===
[full new content of article]

For LINK:
=== LINK: filename.md ===
[full content with fixed/added [[links]]]

STRICT FORMAT RULES:
- Each operation is a separate block
- Block header must be exactly: === OPERATION: filename.md === (uppercase operation name, no extra spaces)
- Content immediately follows the header on the next line
- Blocks are separated by a blank line
- For DELETE: no content, just the header line
- Only output blocks for articles that need changes, skip unchanged ones
- File names in English, lowercase with hyphens
- Use [[concept name]] syntax for all internal links
- Do NOT wrap output in markdown code blocks

Wiki articles:
{text}
"""
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return response.text

def execute_command(text):
    pattern = re.compile(r'=== (MERGE|DELETE|UPDATE|LINK): (.+?\.md)(?:\s*\(FROM:\s*(.+?)\))? ===')
    matches = list(pattern.finditer(text))
    modified_files = []
    for i, match in enumerate(matches):
        operation = match.group(1)
        filename = match.group(2)
        content_start = match.end()
        content_end = matches[i+1].start() if i+1 < len(matches) else len(text)
        content = text[content_start:content_end].strip()
        if operation == "DELETE":
            (WIKI_DIR / filename).unlink(missing_ok=True)
        else:
            (WIKI_DIR / filename).write_text(content, encoding="utf-8")
            modified_files.append(WIKI_DIR / filename)
            if operation == "MERGE" and match.group(3):
                for src in match.group(3).split(","):
                    (WIKI_DIR / src.strip()).unlink(missing_ok=True)
    return modified_files

def build_overview(text):
    prompt=f"""
  You are a knowledge base organizer. Based on the following wiki articles, generate a master overview document.
  REQUIREMENTS:
  - Group articles by topic using ## subheadings
  - Each article gets one line: [[article name]] — one sentence description (under 15 words)
  - Only include articles that exist, do not invent new ones
  - Write in English
  - Do NOT wrap output in markdown code blocks
  Wiki articles:
  {text}
    """
    response =client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    (WIKI_DIR / "_overview.md").write_text(response.text, encoding="utf-8")

if __name__ == "__main__":
    articles_batches=read_articles()
    combined_text=""
    modified_files=[]
    for batch in articles_batches:
        command=get_command(batch)
        print(f"\n{command}")
        modified_files+=execute_command(command)
        combined_text+=batch
    build_overview(combined_text)
    build_index.create_index(build_index.client, force=False)
    build_index.index_wiki(build_index.client, files=modified_files)