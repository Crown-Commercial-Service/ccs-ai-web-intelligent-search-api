
import os

os.environ["AZURESEARCH_FIELDS_CONTENT_VECTOR"] = "text_vector"
os.environ["AZURESEARCH_FIELDS_CONTENT"] = "chunk"
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from langchain_community.vectorstores.azuresearch import AzureSearch
from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI
from src.multiturn_utils import build_graph, answer_once
from langgraph_checkpoint_cosmosdb import CosmosDBSaver

from fastapi import  FastAPI
import pandas as pd
import io
from pydantic import BaseModel



load_dotenv()

graphs = {}
embeddings: AzureOpenAIEmbeddings = AzureOpenAIEmbeddings(
    azure_deployment=os.getenv("EMBEDDING_MODEL_NAME"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("EMBEDDING_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_KEY"),
)

# Configure Vector Store
vector_store: AzureSearch = AzureSearch(
    azure_search_endpoint=os.getenv("VECTOR_STORE_ENDPOINT"),
    azure_search_key=os.getenv("VECTOR_STORE_KEY"),
    index_name=os.getenv("VECTOR_STORE_INDEX"),
    embedding_function=embeddings.embed_query,
    content_key="chunk")

# Configure LLM
llm = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    azure_deployment=os.getenv("DEPLOYMENT_NAME"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    temperature=0.0
)
COSMOS_DB_NAME = os.getenv("COSMOS_DB_NAME")
COSMOS_CONTAINER_NAME = os.getenv("COSMOS_CONTAINER_NAME")

checkpointer = CosmosDBSaver(
    database_name=COSMOS_DB_NAME,
    container_name=COSMOS_CONTAINER_NAME
)


app = FastAPI()
class SearchQuery(BaseModel):
    user_id:str
    query:str

def load_files_for_links():
    try:
        credential = DefaultAzureCredential()
        blob_service_client = BlobServiceClient(account_url=os.getenv('BLOB_URL'), credential=credential)
        container_client = blob_service_client.get_container_client(os.getenv("BLOB_CONFIG_CONTAINER"))
        blob_client = container_client.get_blob_client("CI_document_URLs.csv")
        blob_data = blob_client.download_blob()
        URLS = pd.read_csv(io.BytesIO(blob_data.readall()))
        URLS = URLS.rename(columns={"FileName": "File Name", "AzureURL": "File URL"})
        return URLS
    except Exception as e:
        print(f"Error loading CSV from Blob Storage: {e}")
        URLS = pd.DataFrame()  # Create an empty DataFrame on failure
        return URLS

@app.post("/results")
def ai_search_api(query: SearchQuery):

    # load csv with files for links
    URLS = load_files_for_links()

    # store past query in cosmodb and pull it out for llm based on user_id

    # give it to LLM
    if query.user_id not in graphs:
        graphs[query.user_id] = build_graph(llm=llm, vector_store=vector_store, checkpointer=checkpointer)
    graph = graphs[query.user_id]

    config = {"configurable": {"thread_id": query.user_id}}
    # answer_once(graph=graph, user_input=query.query,config=config,thread_id=query.user_id)
    response = answer_once(graph=graph, user_input=query.query,config=config,thread_id=query.user_id)

    return response

# uvicorn chatbot_api:app --reload --host 127.0.0.1 --port 5000
#  curl -X POST "http://127.0.0.1:5000/results"      -H "Content-Type: application/json"      -d '{"user_id": "abc","query": "what is  1+1"}'