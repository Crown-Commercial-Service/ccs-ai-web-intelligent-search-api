import os
from dotenv import load_dotenv
from ccs_website_data import  fetch_all_ccs_frameworks
import requests
from azure.storage.blob import BlobClient
from pathlib import Path
import zipfile
import io
import shutil

load_dotenv()
ccs_frameworks = fetch_all_ccs_frameworks()
# base_url = "https://webprod-cms.crowncommercial.gov.uk/wp-json/ccs/v1/frameworks/RM6200"
# temporary code on line 13 as my pc turned off and stop downloading the files
ccs_frameworks = ccs_frameworks[149:]
# response = requests.get(base_url)
# print(response.json())
# you need to check the description and documents
# you will need 2 llms one that specialises in looking at the description
# LLM simple search api given input give a list of titles based on live not live


#get df and loop through all titles and download files into blob storage so it can be used for RAG
base_url = os.getenv("BASE_URL")
def zip_checker(url, data, excluded_extension=('.odt', '.docx', '.xlsx', 'pdf')):
    ZIP_MAGIC = b'\x50\x4b\x03\x04'
    binary_data = data.content
    extension = Path(url)
    if extension.suffix in excluded_extension:
        return False
    # if bytes is less than 4 then it cannot be zip
    if len(binary_data) < 4:
        return False
    return binary_data[:4] == ZIP_MAGIC



# def unzipper(data):
#     unzipped_files = []
#     zip_stream = io.BytesIO(data.content)
#     # have save the data in RAM
#     dir = Path.cwd() / "unzipped_data"
#     dir.mkdir(parents=True, exist_ok=True)
#     with zipfile.ZipFile(zip_stream, 'r') as zip_ref:
#         zip_ref.extractall(path=dir)
#     for file in dir.iterdir():
#         if zipfile.is_zipfile(file):
#             # add functionality to recursive find zip files and unzip so it can be added to unzipped_files
#             pass
#         else:
#             unzipped_files.append(file)
#     return unzipped_files

def unzipper_v2(data):
    base_dir = Path.cwd() / "unzipped_data"
    base_dir.mkdir(parents=True, exist_ok=True)
    zip_stream = io.BytesIO(data.content)
    return extract_recursive(zip_stream, base_dir)

def extract_recursive(zip_input, extract_to, excluded_extension=('.odt', '.docx', '.xlsx', 'pdf'), excluded_filenames = ['mimetype', '.DS_Store', 'thumbs.db']):
    unzipped_files = []
    with zipfile.ZipFile(zip_input, 'r') as zip_ref:
        zip_ref.extractall(path=extract_to)

    # Get a list of items inside 'unzipped_data'
    extracted_items = list(extract_to.iterdir())

    # If there is exactly one item and it's a directory, move our 'target' inside it
    if len(extracted_items) == 1 and extracted_items[0].is_dir():
        target_dir = extracted_items[0]
    else:
        target_dir = extract_to

    for item in target_dir.iterdir():
        print(item)
        if item.is_file() and zipfile.is_zipfile(item) and item.suffix not in excluded_extension:
            nested_dir = item.with_suffix('')
            nested_dir.mkdir(exist_ok=True)
            unzipped_files.extend(extract_recursive(item, nested_dir))
            # Remove the nested .zip file after extraction
            item.unlink()
        elif item.is_file() and item.suffix != ".xml" and item.suffix != ".rdf" and item.name.lower() not in excluded_filenames:
            unzipped_files.append(item)

    return unzipped_files






    print("unzipped files")
    #

    # get full filepaths



def agreement_docs( frame_work):
    try:
        new_url = base_url + frame_work
        response = requests.get(new_url)
        data = response.json()
        print(f"This is the data: {data}")
        documents = data['documents']
        return documents
    except Exception as e:
        print(f"This the error that caused the failed download {e}")


def get_rm_page_data():
    for index, row  in ccs_frameworks.iterrows():
        frame_work = row["rm_number"]
        print(f"position:{index} frame_work:{frame_work}")
        documents = agreement_docs(frame_work)
        # new_url = base_url + frame_work
        # response = requests.get(new_url)
        # data = response.json()
        # print(f"This is the data: {data}")
        # documents = data['documents']
        # Guard clause: if agreement_docs returns None/Empty, skip to next framework
        if not documents:
            continue
        for doc in documents:
            try:
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
                    try:
                        data_to_unzip = unzipper_v2(response)
                        for unzipped_file in data_to_unzip:
                            azure_file_name = Path(unzipped_file).name
                            blob_client = BlobClient.from_connection_string(
                                conn_str=os.getenv("BLOB_CONNECTION_STRING"),
                                container_name=os.getenv("BLOB_CONTAINER_NAME"),
                                blob_name=azure_file_name
                            )
                            with open(unzipped_file, "rb") as file:
                                blob_client.upload_blob(data=file, overwrite=True
                                                        )
                    finally:
                        unzipped_dir = Path.cwd() / "unzipped_data"
                        if unzipped_dir.exists() and unzipped_dir.is_dir():
                            print(f"Cleaning up: {unzipped_dir}")
                            # shutil still handles the recursive deletion best
                            shutil.rmtree(unzipped_dir)
            except Exception as e:

                print(f"This the error that caused the failed download {e}")



    # delete unzipped_data folder





get_rm_page_data()