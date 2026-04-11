import pathlib
import re
from google import genai
from dotenv import load_dotenv
import os 

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
WIKI_DIR = pathlib.Path(__file__).parent.parent / "wiki"

client = genai.Client(api_key=API_KEY)

def get_all_filenames():
    mapping = {}
    for f in WIKI_DIR.glob("**/*.md"):
        if f.name != "_index.md":
            mapping[f.stem.lower()] = f.stem
    return mapping

def get_broken_links(filename_map):
    broken = set()
    pattern = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]*)?\]\]')
    for f in WIKI_DIR.glob("**/*.md"):
        for match in pattern.finditer(f.read_text(encoding="utf-8")):
            link_name = match.group(1).strip()
            if link_name not in filename_map.values():
                broken.add(link_name)
    return broken

def read_wiki_summary():
    files = [f for f in WIKI_DIR.glob("**/*.md") if f.name != "_index.md"]
    combined = ""
    for f in sorted(files):
        content = f.read_text(encoding="utf-8")[:300]
        combined += f"\n\n--- {f.stem} ---\n{content}"
    return combined

def run_lint():
    filename_map = get_all_filenames()
    broken_links = get_broken_links(filename_map)
    wiki_summary = read_wiki_summary()
    article_list = "\n".join(sorted(filename_map.values()))

    prompt = f"""
You are a knowledge base editor. Analyze the following wiki and perform a full health check.

Existing articles:
{article_list}

Broken links (referenced but no article exists):
{chr(10).join(f"- [[{b}]]" for b in sorted(broken_links)) if broken_links else "None"}

Wiki content summaries:
{wiki_summary}

Please provide a health check report with these sections:

## 1. Broken Links to Generate
For each broken link, decide:
- GENERATE: this concept deserves its own article
- SKIP: this is too minor, just remove the link

Format:
GENERATE: concept name | one sentence description
SKIP: concept name | reason

## 2. Knowledge Gaps
Concepts that are mentioned but underdeveloped, or important topics missing entirely.
Format: GAP: concept name | what's missing

## 3. Inconsistencies
Contradictions or conflicts between articles.
Format: INCONSISTENCY: article1 vs article2 | description

## 4. New Article Suggestions
Interesting connections or synthesis articles worth writing.
Format: SUGGEST: article name | why it would be valuable

## 5. Articles to Merge
Articles that overlap  significantly or highly relevant details and should be combined.
Format: MERGE: article1 + article2 | reason

## 6. Articles to delete
Delete Articles or concepts that are too detaliled to be remembered or too concrete to be thought as "concept" or "knowledge"
For instance"Amazon OpenSearch Service Version Upgrades" is not essentially any knowledge.it's an detail in within the larger picture.
especially those found in technical tocument. 
Format: Delete article name | reason

Write in English. Be specific and actionable.
"""

    print("Running wiki health check...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text, broken_links, filename_map

def parse_generates(report):
    generates = []
    for line in report.split("\n"):
        line = line.strip()
        if line.startswith("GENERATE:"):
            parts = line[9:].split("|", 1)
            if parts:
                concept = parts[0].strip()
                desc = parts[1].strip() if len(parts) > 1 else ""
                generates.append((concept, desc))
    return generates

def generate_articles(concepts, filename_map):
    if not concepts:
        print("No articles to generate.")
        return

    index = WIKI_DIR / "_index.md"
    index_content = index.read_text(encoding="utf-8") if index.exists() else ""
    article_list = "\n".join(sorted(filename_map.values()))

    prompt = f"""
You are a knowledge base compiler. Generate wiki articles for the following concepts.

Existing articles (use these for [[links]]):
{article_list}

Context from wiki index:
{index_content[:1000]}

For each concept write:
1. Concept explanation (2-3 paragraphs)
2. Key Takeaways (bullet points)
3. Connections to Other Concepts ([[links]] to existing articles only)

Concepts to generate:
{chr(10).join(f"- {c[0]}: {c[1]}" for c in concepts)}

Output format: === FILE: concept name.md === on its own line before each article.
Write in English. Do NOT wrap in markdown code blocks.
Only use [[links]] to articles that exist in the existing articles list above.
"""

    print(f"\nGenerating {len(concepts)} new articles...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    sections = response.text.split("=== FILE:")
    saved = 0
    for section in sections:
        section = section.strip()
        if not section:
            continue
        lines = section.split("\n", 1)
        filename = lines[0].strip().rstrip("===").strip()
        filename = filename.replace("\\", "-").replace("/", "-").replace(":", "-").replace("*", "-").replace("?", "-").replace('"', "-").replace("<", "-").replace(">", "-").replace("|", "-")
        content = lines[1].strip() if len(lines) > 1 else ""
        if filename.endswith(".md"):
            filepath = WIKI_DIR / filename
            filepath.write_text(content, encoding="utf-8")
            print(f"  Saved: {filename}")
            saved += 1
    print(f"  {saved} articles saved.")

def rebuild_index():
    files = [f for f in WIKI_DIR.glob("**/*.md") if f.name != "_index.md"]
    if not files:
        return

    prompt = "Based on the following wiki articles, generate a _index.md master index.\n\nRequirements:\n1. Every article name MUST use [[article name]] Obsidian link format\n2. Group by topic with ## subheadings\n3. One sentence summary per article, under 15 words\n4. Write in English\n5. Do NOT wrap in markdown code blocks\n\nArticle summaries:\n"
    for f in sorted(files):
        content = f.read_text(encoding="utf-8")[:200]
        prompt += f"\n\n{f.name}:\n{content}"

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    if text.endswith("```"):
        text = text.rsplit("\n", 1)[0]

    (WIKI_DIR / "_index.md").write_text(text.strip(), encoding="utf-8")
    print("  _index.md updated.")

if __name__ == "__main__":
    print("=" * 50)
    print("WIKI HEALTH CHECK")
    print("=" * 50)

    report, broken_links, filename_map = run_lint()

    # 保存报告
    report_path = WIKI_DIR.parent / "output" / "lint_report.md"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved to: lint_report.md")
    print("\n" + report)

    # 处理需要生成的文章
    generates = parse_generates(report)
    if generates:
        print(f"\n{'=' * 50}")
        print(f"Found {len(generates)} concepts to generate:")
        for concept, desc in generates:
            print(f"  + {concept}: {desc}")

        confirm = input("\nGenerate these articles? (yes/no): ").strip().lower()
        if confirm == "yes":
            generate_articles(generates, filename_map)
            print("\nRebuilding _index.md...")
            rebuild_index()
            print("\nDone! Run fix_links.py if needed.")
        else:
            print("Skipped.")
    else:
        print("\nNo new articles to generate.")

    print("\nHealth check complete.")