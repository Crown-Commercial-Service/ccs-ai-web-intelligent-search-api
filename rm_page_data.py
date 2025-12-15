import os
from dotenv import load_dotenv
from ccs_website_data import  fetch_all_ccs_frameworks
import requests
from azure.storage.blob import BlobClient
from pathlib import Path
import zipfile
import io
load_dotenv()
ccs_frameworks = fetch_all_ccs_frameworks()
# base_url = "https://webprod-cms.crowncommercial.gov.uk/wp-json/ccs/v1/frameworks/RM6200"

# response = requests.get(base_url)
# print(response.json())
# you need to check the description and documents
# you will need 2 llms one that specialises in looking at the description
# LLM simple search api given input give a list of titles based on live not live


#get df and loop through all titles and download files into blob storage so it can be used for RAG
base_url = "https://webprod-cms.crowncommercial.gov.uk/wp-json/ccs/v1/frameworks/"
def zip_checker(url, data, excluded_extention=('.odt', '.docx', '.xlsx', 'pdf')):
    ZIP_MAGIC = b'\x50\x4b\x03\x04'
    binary_data = data.content
    extension = Path(url)
    if extension.suffix in excluded_extention:
        return False
    # if bytes is less than 4 then it cannot be zip
    if len(binary_data) < 4:
        return False
    return binary_data[:4] == ZIP_MAGIC


def unzipper(data):
    unzipped_files = []
    zip_stream = io.BytesIO(data.content)
    # have save the data in RAM
    dir = Path.cwd() / "unzipped_data"
    dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_stream, 'r') as zip_ref:
        zip_ref.extractall(path=dir)

    print("unzipped files")
    #

    # get full filepaths





def get_rm_page_data():
    for index, row  in ccs_frameworks.iterrows():
        frame_work = row["rm_number"]
        new_url = base_url + frame_work
        response = requests.get(new_url)
        data = response.json()

        documents = data['documents']
        for doc in documents:
            print(doc["title"], doc["url"])
            data_url = doc["url"]

            response = requests.get(data_url, stream=True)
            is_zip = zip_checker(data_url, response)
            if is_zip is False:
                azure_file_name = Path(data_url).name
                blob_client = BlobClient.from_connection_string(
                    conn_str=os.getenv("BLOB_CONNECTION_STRING"),
                    container_name=os.getenv("BLOB_CONTAINER_NAME"),
                    blob_name=azure_file_name
                )
                blob_client.upload_blob(data=response.content, overwrite=True
                                        )
            if is_zip is True:
                data_to_unzip = unzipper(response)
                for unzipped_file in data_to_unzip:
                    azure_file_name = Path(unzipped_file).name
                    blob_client = BlobClient.from_connection_string(
                        conn_str=os.getenv("BLOB_CONNECTION_STRING"),
                        container_name=os.getenv("BLOB_CONTAINER_NAME"),
                        blob_name=azure_file_name
                    )
                    blob_client.upload_blob(data=response.content, overwrite=True
                                            )







get_rm_page_data()