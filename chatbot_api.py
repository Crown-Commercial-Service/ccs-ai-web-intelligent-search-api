
import os

os.environ["AZURESEARCH_FIELDS_CONTENT_VECTOR"] = "text_vector"
os.environ["AZURESEARCH_FIELDS_CONTENT"] = "chunk"
from dotenv import load_dotenv
from langchain_community.vectorstores.azuresearch import AzureSearch
from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI
from src.ccs_ai_josh.multiturn_utils import build_graph, answer_once
from langgraph_checkpoint_cosmosdb import CosmosDBSaver

from fastapi import  FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta, timezone
from azure.storage.blob import generate_blob_sas, BlobSasPermissions

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from openai import AsyncAzureOpenAI
from src.wis.ai_docs_filterer_for_RAG import run_rm_labeller
from ccs_website_data import  fetch_all_ccs_frameworks


load_dotenv()

ccs_frameworks = fetch_all_ccs_frameworks()
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

pydantic_azure_client = AsyncAzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    azure_deployment=os.getenv("DEPLOYMENT_NAME"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
)
pydantic_rm_labeller_model = OpenAIChatModel(
    model_name= os.getenv("DEPLOYMENT_NAME"),
    provider=OpenAIProvider(openai_client=pydantic_azure_client)
)

COSMOS_DB_NAME = os.getenv("COSMOS_DB_NAME")
COSMOS_CONTAINER_NAME = os.getenv("COSMOS_CONTAINER_NAME")

checkpointer = CosmosDBSaver(
    database_name=COSMOS_DB_NAME,
    container_name=COSMOS_CONTAINER_NAME
)
#This is to be used to help pydantic ai model categorise user's query

rm_descriptions = "\n".join([
    f"RM: {r.rm_number} | "
    f"Keywords: {r.keywords if 'keywords' in r and str(r.keywords).strip() else 'N/A'} | "
    f"Summary: {r.summary} | "
    f"Pillar: {r.pillar} ({r.category})"
    for _, r in ccs_frameworks.iterrows()
])

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allows your Flask app to talk to FastAPI
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchQuery(BaseModel):
    user_id:str
    query:str


@app.post("/results")
async def ai_search_api(query: SearchQuery):
    """ This function uses a LLM to answer user's query

    :param query (Pydantic): data model(class) to answer query per user user
    :return dictionary: containing AI's response
    """

    # create langchain graph to orchestrate LLM actions
    if query.user_id not in graphs:
        graphs[query.user_id] = build_graph(llm=llm, vector_store=vector_store, checkpointer=checkpointer)
    graph = graphs[query.user_id]
    # prepare data to check for a user id what was their last rm number for filtering
    history_config = {"configurable": {"thread_id": query.user_id}}

    state = graph.get_state(history_config)

    last_known_rm = state.values.get("last_rm_label", "UNKNOWN") if state.values else "UNKNOWN"

    # get RM label(e.g RM6200) from user's query if the label returns unknown it means it is likely a follow question
    try:
        rm_label_result = await run_rm_labeller(pydantic_rm_labeller_model, rm_descriptions, query.query)

        rm_label = rm_label_result.rm_number
        if rm_label == "UNKNOWN":
            print("last known rm:", last_known_rm)
            rm_label = last_known_rm
        reasoning = rm_label_result.reasoning
        print(f"PydanticAI selected {rm_label} because: {reasoning}")
    except Exception as e:
        print(f"Labelling failed: {e}")
        rm_label = last_known_rm
    # Keep the last rm label updated
    graph.update_state(history_config, {"last_rm_label": rm_label})



    config = {"configurable": {"thread_id": query.user_id, "rm_filter": rm_label}}
    response = answer_once(graph=graph, user_input=query.query,config=config,thread_id=query.user_id)
    print(f"user: {query.query}")
    print()
    print(f"AI: {response["answer"]}")
    print()
    print(f"links below:\n {response["source_names"]}")
    sources = list(set(response["source_names"]))
    # return AI response with sources if there is any
    return {"AI_response":response["answer"], "source_content":sources}


@app.get("/get_download_url/{file_name}")
async def get_download_url(file_name: str):
    """ Downloads files from storage that has been retrieved by LLM

    :param file_name(str): name of file to be downloaded from blob
    :return dictionary: Download URL
    """
    # Setup credentials
    account_name = os.getenv('AZURE_STORAGE_ACCOUNT_NAME')
    account_key = os.getenv('AZURE_STORAGE_KEY')
    container_name = os.getenv('BLOB_CONTAINER_NAME')
    blob_url = os.getenv('BLOB_URL')

    # Set expiry for 1 hour
    expiry_time = datetime.now(timezone.utc) + timedelta(hours=1)

    # Generate SAS token with 'attachment' disposition to force download
    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container_name,
        blob_name=file_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=expiry_time,
        # This is the line that forces the "Save As" behavior
        content_disposition=f'attachment; filename="{file_name}"'
    )

    download_url = f"{blob_url.rstrip('/')}/{container_name.strip('/')}/{file_name.lstrip('/')}?{sas_token}"
    print(f"download url: {download_url}")
    return {"download_url": download_url}

# uvicorn chatbot_api:app --reload --host 127.0.0.1 --port 8000
#  curl -X POST "http://127.0.0.1:8000/results"      -H "Content-Type: application/json"      -d '{"user_id": "abc","query": "what is  1+1"}'