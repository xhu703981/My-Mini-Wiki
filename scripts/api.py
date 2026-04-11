from pydantic import BaseModel
from fastapi import FastAPI
from scripts.query_wiki import get_answer

class QueryRequest(BaseModel):
    question:str

app=FastAPI()

@app.post("/query")
def query_endpoint(request:QueryRequest):
    return get_answer(request.question)