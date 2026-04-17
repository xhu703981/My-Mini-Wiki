import json
import pathlib
import random
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
WIKI_DIR = pathlib.Path(__file__).parent.parent / "wiki"
OUTPUT_FILE = pathlib.Path(__file__).parent.parent / "eval_dataset.json"
client = genai.Client(api_key=API_KEY)
JUDGE_MODEL = "gemini-2.5-pro"
PROMPT_TEMPLATE = """You are an expert evaluator building a test dataset for a RAG system.
Given the wiki article below, generate {n} realistic questions a user might ask, along with ideal ground truth answers based ONLY on the article content.
Requirements:
- Questions must be specific and fully answerable from the article
- Ground truth answers must be accurate, complete, and grounded solely in the article
- Vary question types: factual, conceptual, how-to
- Output a JSON array only, no other text: [{{"question": "...", "ground_truth": "..."}}]
Article title: {title}
Article content:
{content}"""

def generate_qa_pairs(title: str, content: str, n: int = 3) -> list[dict]:
    prompt = PROMPT_TEMPLATE.format(title=title, content=content, n=n)
    response = client.models.generate_content(
        model=JUDGE_MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    pairs = json.loads(response.text)
    for pair in pairs:
        pair["source_article"] = title
    return pairs

def main(n_articles: int = 15, qa_per_article: int = 3):
    wiki_files = [f for f in WIKI_DIR.glob("*.md") if f.name != "_overview.md"]
    sample = random.sample(wiki_files, min(n_articles, len(wiki_files)))
    dataset = []
    for wiki_file in sample:
        title = wiki_file.stem
        content = wiki_file.read_text(encoding="utf-8")
        try:
            pairs = generate_qa_pairs(title, content, n=qa_per_article)
            dataset.extend(pairs)
            print(f"  {len(pairs)} pairs")
        except Exception as e:
            print(f"  Error: {e}")
    OUTPUT_FILE.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    print(f"\nSaved {len(dataset)} Q&A pairs -> {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
