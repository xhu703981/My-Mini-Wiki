import pathlib
from google import genai
from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection
import os

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
OPENSEARCH_ENDPOINT = os.getenv("OPENSEARCH_ENDPOINT")
OPENSEARCH_USER = os.getenv("OPENSEARCH_USER")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD")
OUTPUT_DIR = pathlib.Path(__file__).parent.parent / "output"
INDEX_NAME = "wiki-rag"
host = OPENSEARCH_ENDPOINT.replace("https://", "")
gemini_client = genai.Client(api_key=API_KEY)
client=OpenSearch(hosts=[{"host": host, "port": 443}],
        http_auth=(OPENSEARCH_USER, OPENSEARCH_PASSWORD),
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=30)

def search_by_dense(query_vector, k=5):
    query_body={
        "size": k,
        "query": {
        "knn": {
            "embedding": {
            "vector":query_vector,
            "k": k
            }
        }
        }
    }
    response= client.search(index=INDEX_NAME, body=query_body)
    result=[]
    for hit in response["hits"]["hits"]:
        result.append(hit["_source"])
    return result

def search_by_BM25(query_text,k=5):
    query_body= {
    "size": k,
    "query": {
      "match": {
        "content": query_text
      }
    }
    }
    response= client.search(index=INDEX_NAME, body=query_body)
    result=[]
    for hit in response["hits"]["hits"]:
        result.append(hit["_source"])
    return result

def get_embedding(text):
    if not text or not text.strip(): return None
    try:
        response=gemini_client.models.embed_content(model="gemini-embedding-001", contents=text)
        [result] = response.embeddings
        embedding = result.values
        return embedding
    except Exception as e:
        print(f"Error getting embedding: {e}")
        return None

def search_hybrid(query_text,k=5):
    question_embedded=get_embedding(query_text)
    related_cotent_by_dense= search_by_dense(question_embedded, k)
    related_content_by_BM25=search_by_BM25(query_text, k)
    scores={}
    rank=1
    for chunk in related_content_by_BM25:
        key_BM=(chunk["title"],chunk["chunk_id"])
        scores[key_BM]=1/(rank+60)
        rank+=1

    rank=1
    for chunk in related_cotent_by_dense:
        key_dense= (chunk["title"],chunk["chunk_id"])
        if key_dense in scores:
            scores[key_dense]+=1/(rank+60)
        else:
            scores[key_dense]=1/(rank+60)
        rank+=1
    chunks={}
    for chunk in related_content_by_BM25+related_cotent_by_dense:
        key= (chunk["title"],chunk["chunk_id"])
        chunks[key]=chunk
    sorted_keys= sorted(scores,key=lambda x:-scores[x])
    return [(chunks[key], scores[key]) for key in sorted_keys[:k]]

def get_answer(question):  #this is for api specifically
    results = search_hybrid(question)
    context = ""
    for chunk, score in results:
        context += f"\n\n[Article: {chunk['title']} | Relevance: {score:.4f}]\n{chunk['content']}"
    prompt = f"""
You are a knowledgeable assistant answering questions from a personal wiki.
Use the retrieved articles below to answer the question. Each article has a relevance score — higher means more relevant.
Guidelines:
- Answer only based on the provided articles. If the answer isn't there, say "I don't have information on this in my knowledge base."
- Write naturally and conversationally, as if explaining to a curious friend — not like a textbook or encyclopedia
- Build up the explanation gradually; don't dump everything at once
- Cite the articles you used at the end
Retrieved articles:
{context}
Question: {question}
"""
    response = gemini_client.models.generate_content(model="gemini-2.5-flash",contents=prompt)
    answer = response.text
    return answer
    
def query(question):
    answer = get_answer(question)
    OUTPUT_DIR.mkdir(exist_ok=True)
    out_file = OUTPUT_DIR / f"question.md"
    out_file.write_text(f"# {question}\n\n{answer}", encoding="utf-8")
    print(answer)

if __name__ == "__main__":
    while True:
        q = input("Your Question:").strip()
        if q.lower() == "quit": break
        if q: query(q)