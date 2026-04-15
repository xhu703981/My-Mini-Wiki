from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.responses import FileResponse
from scripts.query_wiki import get_answer
from fastapi.middleware.cors import CORSMiddleware

class QueryRequest(BaseModel):
    question:str

app=FastAPI()

app.add_middleware(
      CORSMiddleware,
      allow_origins=["*"],
      allow_methods=["*"],
      allow_headers=["*"],
  )

@app.get("/")
def index():
    return FileResponse("index.html")

@app.post("/query")
def query_endpoint(request:QueryRequest):
    return get_answer(request.question)