# evaluation script to quantify the performance of WIS with a given configuration and prompt
import os
os.environ["AZURESEARCH_FIELDS_CONTENT_VECTOR"] = "text_vector"
os.environ["AZURESEARCH_FIELDS_CONTENT"] = "chunk"

import pandas as pd

from dotenv import load_dotenv
from langchain_community.vectorstores.azuresearch import AzureSearch
from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI
from ccs_ai_josh.multiturn_utils import build_graph, answer_once
from langgraph_checkpoint_cosmosdb import CosmosDBSaver

from fastapi import  FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta, timezone
from azure.storage.blob import generate_blob_sas, BlobSasPermissions

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from openai import AsyncAzureOpenAI
from wis.ai_docs_filterer_for_RAG import run_rm_labeller
from wis.ccs_website_data import fetch_all_ccs_frameworks

from ccs_ai_josh.eval_utils import evaluate_response

load_dotenv()

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
ccs_frameworks = fetch_all_ccs_frameworks()
rm_descriptions = "\n".join([
    f"RM: {r.rm_number} | "
    f"Keywords: {r.keywords if 'keywords' in r and str(r.keywords).strip() else 'N/A'} | "
    f"Summary: {r.summary} | "
    f"Pillar: {r.pillar} ({r.category})"
    for _, r in ccs_frameworks.iterrows()
])

# truthset needs to be downloaded from Google Drive and placed in `data` folder
truthset_file_path = os.path.join("data", "truthset.tsv")
truthset = pd.read_tsv(truthset_file_path)
