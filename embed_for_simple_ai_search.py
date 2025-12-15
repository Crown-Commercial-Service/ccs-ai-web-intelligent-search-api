from ccs_website_data import  fetch_all_ccs_frameworks
from langchain_openai import AzureOpenAIEmbeddings
import os
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from langchain.text_splitter import RecursiveCharacterTextSplitter
import hashlib
from dotenv import load_dotenv

load_dotenv()

ccs_frameworks = fetch_all_ccs_frameworks()

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
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=600,
    chunk_overlap=100
)


# loop over title
for index, row in ccs_frameworks.iterrows():
    title = row['title']
    # text split description
    description = row['description']
    #  use text splitter
    chunks = text_splitter.split_text(description)
    all_docs = []
    for index, chunk in enumerate(chunks):
        id_string = title + chunk
        unique_id = hashlib.md5(id_string.encode("utf-8")).hexdigest()
        # this appends title to each chunk
        enriched_data = f"Title: {title}\nDescription chunk: {chunk}"
        embedded_chunk = embed.embed_query(enriched_data)
        docs =  {
            "id": unique_id,
            "title": title,
            "rm_number":  row["rm_number"],
            "status": row['status'],
            "description": chunk,
            "summary": row["summary"],
            "start_date": str(row['start_date']),
            "regulation": row["regulation"],
            "embedding": embedded_chunk
        }


        all_docs.append(docs)

    if all_docs:
        client.upload_documents(documents=all_docs)


