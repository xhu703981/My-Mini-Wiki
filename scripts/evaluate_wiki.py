import json
import pathlib
import os
import sys
import time
from dotenv import load_dotenv
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from query_wiki import search_hybrid, gemini_client

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
DATASET_FILE = pathlib.Path(__file__).parent.parent / "eval_dataset.json"
OUTPUT_FILE = pathlib.Path(__file__).parent.parent / "output" / "ragas_results.json"
JUDGE_MODEL = "gemini-2.5-pro"
RAG_MODEL = "gemini-2.5-flash"
RETRY_WAIT = 30
ANSWER_PROMPT = """You are a knowledgeable assistant answering questions from a personal wiki.
Use the retrieved articles below to answer the question. Answer only based on the provided articles.
If the answer isn't there, say "I don't have information on this in my knowledge base."
Retrieved articles:
{context}
Question: {question}"""

def retry(fn, *args, **kwargs):
    while True:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            print(f"  [retry] {e} — retrying in {RETRY_WAIT}s...")
            time.sleep(RETRY_WAIT)

def run_rag(question: str, k: int = 5) -> tuple[str, list[str]]:
    results = retry(search_hybrid, question, k=k)
    contexts = [chunk["content"] for chunk, _ in results]
    context_block = ""
    for chunk, score in results:
        context_block += f"\n\n[Article: {chunk['title']} | Relevance: {score:.4f}]\n{chunk['content']}"
    prompt = ANSWER_PROMPT.format(context=context_block, question=question)
    response = retry(gemini_client.models.generate_content, model=RAG_MODEL, contents=prompt)
    return response.text, contexts

def main():
    dataset_raw = json.loads(DATASET_FILE.read_text(encoding="utf-8"))
    print(f"Loaded {len(dataset_raw)} eval samples")
    ragas_llm = LangchainLLMWrapper(ChatGoogleGenerativeAI(model=JUDGE_MODEL, google_api_key=API_KEY))
    ragas_embeddings = LangchainEmbeddingsWrapper(GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=API_KEY))
    metrics = [
        Faithfulness(llm=ragas_llm),
        AnswerRelevancy(llm=ragas_llm, embeddings=ragas_embeddings),
        ContextPrecision(llm=ragas_llm),
        ContextRecall(llm=ragas_llm),
    ]
    samples = []
    for i, item in enumerate(dataset_raw, 1):
        question = item["question"]
        ground_truth = item["ground_truth"]
        print(f"[{i}/{len(dataset_raw)}] {question[:70]}...")
        answer, contexts = run_rag(question)
        samples.append(
            SingleTurnSample(
                user_input=question,
                response=answer,
                retrieved_contexts=contexts,
                reference=ground_truth,
            )
        )
    results = retry(evaluate, dataset=EvaluationDataset(samples=samples), metrics=metrics)
    df = results.to_pandas()
    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    df.to_json(OUTPUT_FILE, orient="records", indent=2)
    print("\n=== RAGAS Results ===")
    for col in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        if col in df.columns:
            print(f"  {col}: {df[col].mean():.4f}")
    print(f"\nFull results -> {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
