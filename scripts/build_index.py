import os
from dotenv import load_dotenv
from google import genai
from opensearchpy import OpenSearch, RequestsHttpConnection
import pathlib

load_dotenv()

#配置
API_KEY = os.getenv("GEMINI_API_KEY")
OPENSEARCH_ENDPOINT = os.getenv("OPENSEARCH_ENDPOINT")
OPENSEARCH_USER = os.getenv("OPENSEARCH_USER")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD")
WIKI_DIR = pathlib.Path(__file__).parent.parent / "wiki"
INDEX_NAME = "wiki-rag"

#client
gemini_client=genai.Client(api_key=API_KEY)
host=OPENSEARCH_ENDPOINT.replace("https://", "")
client=OpenSearch(hosts=[{"host": host, "port": 443}],
        http_auth=(OPENSEARCH_USER, OPENSEARCH_PASSWORD),
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=30)

#Methods
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
    
def create_index(client,force):
    index_name = INDEX_NAME
    index_body = {
        'settings': {
            'index.knn': True,  
            'knn.algo_param.ef_search': 100 
        },
        'mappings': {
            'properties': {
                'title': {'type': 'keyword'}, 
                'chunk_id': {'type': 'integer'},
                'content': {'type': 'text'},
                'embedding': { 
                    'type': 'knn_vector',
                    'dimension': 3072, 
                    'method': {
                        'name': 'hnsw',
                        'space_type': 'cosinesimil',
                        'engine': 'faiss',
                        'parameters': {
                            'ef_construction': 200,
                            'm': 16
                        }
                    }
                }
            }
        }
    }
    if client.indices.exists(index=index_name):
        if force:
            client.indices.delete(index=index_name)
            print(f"Deleted old index: {index_name}")
        else:
            print("skipping.")
            return
    client.indices.create(index=index_name, body=index_body)

def chunck_text(text,chunking_size=6000,overlap=300):  # use when text exceeds the context window of gemini, 6000 size=1500tokens(limit:2048)
    chuncks=[]
    start=0
    while(start<len(text)):
        end=start+chunking_size
        chuncks.append(text[start:end])
        start=end-overlap
    return chuncks

def index_wiki(client,files=None):
    if files is None:
          files = [f for f in WIKI_DIR.glob("*.md") if not f.name.startswith("_")]
    print(f" found {len(files)} articles")
    for f in files:
        content=f.read_text(encoding="utf-8")
        title=f.stem #filename
        if len(content)>=6000:
            chunks=chunck_text(content)
        else:
            chunks=[content]
        for i,chunk in enumerate(chunks):
            text_to_embedd=f"{title}\n\n{chunk}"
            text_after_embedding=get_embedding(text_to_embedd)
            if text_after_embedding is None:
                print(f"Skipping chunk")
                continue
            doc={
                "title": title, #metadata
                "chunk_id": i,  
                "content": chunk,
                "embedding": text_after_embedding
            }
            client.index(index=INDEX_NAME,id=f"{title}_chunk_{i}",body=doc)
        print(f"indexed{i+1}articles already")

if __name__ == "__main__":
    create_index(client,False)
    index_wiki(client)




