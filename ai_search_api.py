from langchain_openai import AzureOpenAIEmbeddings
from dotenv import load_dotenv
import os
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from fastapi import  FastAPI
from reranker import rerank_list
from pydantic import BaseModel

load_dotenv()

embed = AzureOpenAIEmbeddings(
    model= os.getenv("EMBEDDING_MODEL_NAME"),
    api_key= os.getenv("AZURE_OPENAI_KEY"),
    azure_endpoint= os.getenv("EMBEDDING_ENDPOINT"),
    api_version= os.getenv("AZURE_OPENAI_API_VERSION")
)

client = SearchClient(
    endpoint=os.getenv("SEARCH_ENDPOINT"),
    index_name=os.getenv("SEARCH_INDEX"),
    credential=AzureKeyCredential(os.getenv("ADMIN_KEY"))
)

app = FastAPI()

class SearchQuery(BaseModel):
    query: str
    total_results: int
    status: str




@app.post("/results")
def ai_search_api(query: SearchQuery):

    query_vector = embed.embed_query(query.query.upper())
    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=40,  # Increase search window to find enough unique matches
        fields="embedding"
    )
    filter_expr = f"status eq '{query.status}'" if query.status else None
    results = client.search(
        search_text=None,
        vector_queries=[vector_query],
        filter=filter_expr,
        select=["title", "rm_number", "description", "status"],
        top=40
    )

    top_results = []
    seen_titles = set()

    for res in results:
        title = res['title']

        # Check if we've already added this framework title
        if title not in seen_titles:
            top_results.append(res)
            seen_titles.add(title)

        # Stop exactly once we have 10 unique documents
        if len(top_results) == query.total_results:
            break
    new_results = rerank_list(user_query=query.query, results=top_results)

    return new_results

#uvicorn ai_search_api:app --reload --host 127.0.0.1 --port 5000
# curl -X POST "http://127.0.0.1:5000/results"      -H "Content-Type: application/json"      -d '{"query": "AI", "tal_results": 10, "status": "expired"}'
