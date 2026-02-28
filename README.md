# web_intelligent_search_api

This repo contains:

- **Flask UI**: `dummy_flask_app2.py` (renders `templates/index_v2.html`, `templates/results.html`, `templates/agreement.html`)
- **FastAPI backend (optional)**: `chatbot_api.py` (powers the right-side “CCS Assistant” chat + source download links)

## Developer Tooling (Pre-commit, Ruff, pytest)

This project uses:

- [pre-commit](https://pre-commit.com/) for running checks automatically before each commit.
- [Ruff](https://docs.astral.sh/ruff/) for fast linting.
- [pytest](https://docs.pytest.org/) for unit testing.

### Install tooling

If you already installed dependencies from `requirements.txt`, install the remaining developer tools:

```bash
python -m pip install pre-commit ruff
```

Or install all at once:

```bash
python -m pip install -r requirements.txt pre-commit ruff
```

### Set up pre-commit hooks

Install hooks locally:

```bash
pre-commit install
```

Run all hooks manually across the repository:

```bash
pre-commit run --all-files
```

### Run Ruff and pytest manually

Run Ruff:

```bash
ruff check .
```

Run tests:

```bash
pytest -q
```

## Pages / routes (Flask UI)

- **`/`**: login page (`templates/login.html`)
- **`/index`**: homepage (`templates/index_v2.html`)
  - “Search agreements” submits a GET form to `/results?q=...`
  - `q` is currently **ignored** (no filtering)
- **`/results`**: search results page (`templates/results.html`)
  - Renders **all agreements** from `website_agreement_data2.csv`
  - Left-hand filters are **UI-only** (do not filter yet)
  - Each agreement title links to `/agreement/<rm_number>`
- **`/agreement/<rm_number>`**: agreement detail page (`templates/agreement.html`)
  - CCS-style layout with right-hand panels and accordion sections
  - Sections (Description/Benefits/Products and suppliers/How to buy/Documents) are **accordions**

## Data source

The results + agreement pages are **server-rendered from**:

- `website_agreement_data2.csv`

`dummy_flask_app2.py` reads the CSV on each request and maps fields like:
`title`, `rm_number`, `start_date`, `end_date`, `summary`, `description`, `benefits`, `how_to_buy`, `regulation`, and parsed `lots`.

## CCS framework ingestion script

`ccs_website_data.py` fetches framework data from the CCS public API and returns a pandas DataFrame.

### Unit tests

Basic business logic tests for this module are in:
- `tests/test_ccs_website_data.py`

Run them with:
- `pytest tests/test_ccs_website_data.py`

## Azure setup for RAG system

The application utilizes Azure AI Search as its
RAG vector database and Azure Blob Storage to
host the source documents.
Our architecture implements a dual-LLM design
to optimize performance and accuracy. Below describes each part of the architecture.

- RM labeller (Pydantic AI) :A framework that prioritizes speed and type safety. Because the core validation logic is implemented in Rust, it offers a leaner execution model than LangChain, requiring fewer function calls to process data and return results.
- Langchain LLM (Langchain and Langgraph): The standard LLM library for conversation AI that returns the user answer based on filtering of the Pydantic AI model.

The RM Labeller component ensures only relevant RAG documents reach the LLM. Using a specialized system prompt, the labeller maps user queries to specific RM numbers. This filtering mechanism prevents "noise" by narrowing the document retrieval scope before the final answer is generated.
## Blob Storage setup for Filtering mechanism

To enable the filtering mechanism to work, the blob storage must store
the metadata for each file (RM number) so that the RAG vector database
can use that to filter. Here are steps below to set up a blob storage for filtering functionality:
 1.  Create a blob storage in azure that is private
 2.  if you are using the CCS website data run `rm_page_data.py`
    make sure you have the environment variables for BLOB_CONNECTION_STRING, BLOB_CONTAINER_NAME and also the website ccs api url  called BASE_URL
3. This script will automatically download the files alongside the rm number  in the metadata.

Once the blob storage been populated with the files and metadata containing the rm number you have successfully created the blob storage for the filtering mechanism and now are ready to create the Azure RAG Vector Database.

## Azure RAG Vector Database Set up for Filtering Mechanism
After setting up your blob storage you then need to set up AI Azure search, the steps follow below:
1. Set up AI Azure Search
2. Click on Import data(new) and follow the through the pages, make sure
    Semantic Ranker has been  ticked
3. Once the RAG has been created you have to go into the indexes which in search management
  and click on the created RAG index and click edit JSON and add column below
vector database :
   -   ` {
         "name": "rm_number",
         "type": "Edm.String",
         "searchable": true,
         "filterable": true,
         "retrievable": true,
         "stored": true,
         "sortable": true,
         "facetable": true,
         "key": false,
         "analyzer": "keyword",
         "synonymMaps": []
       }`
4. Now go into indexers in search management and click on the RAG you created
    and click on edit json and change datatoExtract(which is in configurations within parameters) to `"contentAndMetadata"`
5. within the same json  within outputFieldMappings add:
   - `{
      "sourceFieldName": "/document/rm_number",
      "targetFieldName": "rm_number",
      "mappingFunction": null
    }`

6. Now within Search management go to Skillsets and click on the name of RAG you created, this will
open a json file and then you must go to mappings list and you must add:
   -    `{
            "name": "rm_number",
            "source": "/document/rm_number",
            "inputs": []
          }`

Once you have done all the 6 steps you have successfully created your RAG system to allow for filtering.

## Running the App with filtering

Once blob storage and RAG vector database has created, you can now run model with or without UI, here are the environment variables
you need :
- Without UI just API:
`AZURE_OPENAI_API_VERSION
    AZURE_OPENAI_ENDPOINT
    AZURE_OPENAI_KEY
    DEPLOYMENT_NAME
    VECTOR_STORE_ENDPOINT
    VECTOR_STORE_KEY
    VECTOR_STORE_INDEX
    COSMOSDB_ENDPOINT
    COSMOSDB_KEY
    COSMOS_DB_NAME
    COSMOS_CONTAINER_NAME
    AZURE_STORAGE_ACCOUNT_NAME
    AZURE_STORAGE_KEY
    BLOB_CONTAINER_NAME =
    EMBEDDING_MODEL_NAME
    EMBEDDING_ENDPOINT
    BLOB_URL `

run these commands to use api only :

 1. `uvicorn chatbot_api:app --reload --host 127.0.0.1 --port 8000`
2. `curl -X POST "http://127.0.0.1:8000/results"      -H "Content-Type: application/json"      -d '{"user_id": "abc","query": "what is  1+1"}'`

- With UI(have all environment variables above and the runs below):
     `WEBSEARCH_API_URL
    DOWNLOAD_SOURCE_URL
    TEST_ACCESS_KEY `

run `dummy_flask_app2.py` providing if you using the deployed version of this app that is on azure if you do not have this then you must
also do the commands for the api only instructions(follow only step 1) and add the local host url for `WEBSEARCH_API_URL` and `DOWNLOAD_SOURCE_URL`. `TEST_ACCESS_KEY ` can be anything if
you are working locally but if you want to use the deployed version of the app you must contact the AI team for that.

## Experiment results for query filter capability

Currently, the accuracy for the filter mechanism is 77.9% (aiming to improve this) this is on 19 frameworks and 5 question for each framework.
The questions were made using gemini. The file was not uploaded to repo but if you want to have it contact AI Team.
