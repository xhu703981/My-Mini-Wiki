import pathlib
from google import genai
from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection
import os

# ===== 配置 =====
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
        "size": 5,
        "query": {
        "knn": {
            "embedding": {
            "vector":query_vector,
            "k": 5
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
    query_body=  {
    "size": 5,
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
    if not text or not text.strip():
        return None
    try:
        response=gemini_client.models.embed_content(model="gemini-embedding-001", contents=text)
        if not response.embeddings:
            return None
        [result] = response.embeddings
        embedding = result.values
        if embedding and len(embedding) == 3072:
            return embedding
        else:
            print(f"Invalid embedding length: {len(embedding) if embedding else 0}")
            return None    
    except Exception as e:
        print(f"Error getting embedding: {e}")
        return None

def search_hybrid(query_text,k=5):
    question_embedded=get_embedding(query_text)
    related_cotent_by_dense= search_by_dense(question_embedded, k=5)
    related_content_by_BM25=search_by_BM25(query_text, k=5)
    scores={}
    rank=1
    for chunk in related_content_by_BM25:
        key_BM=(chunk["title"],chunk["chunk_id"])
        content_text_BM=chunk["content"]
        scores[key_BM]=1/(rank+60)
        rank+=1

    rank=1
    for chunk in related_cotent_by_dense:
        key_dense= (chunk["title"],chunk["chunk_id"])
        context_text_dense=chunk["content"]
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
    return [chunks[key] for key in sorted_keys[:k]]
    
        
    
def query(question):
    results = search_hybrid(question)
    context = ""
    for chunk in results:
        context += f"\n\n--- ARTICLE: {chunk['title']} ---\n{chunk['content']}"
    prompt = f"""
你是一个知识库问答助手。基于以下知识库内容回答问题。

要求：
1. 只根据知识库内容回答，不要编造
2. 格式清晰
3. 如果涉及多个概念，用标题分隔
4. 最后列出参考了哪些文章

知识库内容：
{context}

问题：{question}
"""
    print(f"\n问题：{question}")
    print("正在查询...\n")
    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    answer = response.text
    OUTPUT_DIR.mkdir(exist_ok=True)
    safe_name = "".join(c for c in question[:30] if c.isalnum() or c in " _-")
    out_file = OUTPUT_DIR / f"{safe_name.strip()}.md"
    out_file.write_text(f"# {question}\n\n{answer}", encoding="utf-8")
    print(answer)
    print(f"\n已保存到: {out_file.name}")

if __name__ == "__main__":
    print("输入 quit 退出\n")
    while True:
        q = input("你的问题：").strip()
        if q.lower() == "quit":
            break
        if q:
            query(q)