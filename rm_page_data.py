import os
from dotenv import load_dotenv
from ccs_website_data import  fetch_all_ccs_frameworks
import requests
from azure.storage.blob import ContainerClient, ExponentialRetry
from pathlib import Path
import zipfile
import io
import shutil
import re
import time

load_dotenv()
ccs_frameworks = fetch_all_ccs_frameworks()

ccs_frameworks = ccs_frameworks[0:4]
allowed_filetypes = ('.odt', '.docx', '.pdf', ".txt")

#get df and loop through all titles and download files into blob storage so it can be used for RAG
base_url = os.getenv("BASE_URL")
def zip_checker(url, data):
    ZIP_MAGIC = b'\x50\x4b\x03\x04'
    binary_data = data.content
    extension = Path(url)
    if extension.suffix in allowed_filetypes:
        return False
    # if bytes is less than 4 then it cannot be zip
    if len(binary_data) < 4:
        return False
    return binary_data[:4] == ZIP_MAGIC




def unzipper_v2(data, rm_number):
    base_dir = Path.cwd() / "unzipped_data"
    base_dir.mkdir(parents=True, exist_ok=True)
    zip_stream = io.BytesIO(data.content)
    return extract_recursive(zip_stream, base_dir, rm_number)


def extract_recursive(zip_input, extract_to, rm_number,
                      excluded_filenames=['mimetype', '.DS_Store', 'thumbs.db']):
    unzipped_files = []
    with zipfile.ZipFile(zip_input, 'r') as zip_ref:
        zip_ref.extractall(path=extract_to)

    # list() creates a snapshot so we don't iterate over changing filenames
    current_items = list(extract_to.rglob('*'))

    for item in current_items:
        if not item.is_file():
            continue

        # 1. Handle Nested Zips
        if zipfile.is_zipfile(item) and item.suffix not in allowed_filetypes:
            nested_dir = item.with_suffix('')
            nested_dir.mkdir(exist_ok=True)
            unzipped_files.extend(extract_recursive(item, nested_dir, rm_number))
            item.unlink()

            # 2. Handle Valid Files

        elif item.suffix in allowed_filetypes and  item.name not in excluded_filenames:
            # ^RM\d+ matches RM + digits at the start. [_ ]* matches any underscores or spaces following.
            clean_name = re.sub(r'^RM\d+[_ ]*', '', item.name, flags=re.IGNORECASE)

            new_name = f"{rm_number}_{clean_name}"
            new_path = item.with_name(new_name)

            try:
                # Only rename if the current name isn't already perfect
                if item.name != new_name:
                    item.rename(new_path)
                    unzipped_files.append(new_path)
                else:
                    unzipped_files.append(item)
            except FileNotFoundError:
                if new_path.exists():
                    unzipped_files.append(new_path)

    return unzipped_files





def agreement_docs( frame_work):
    try:
        new_url = base_url + frame_work
        response = requests.get(new_url)
        data = response.json()
        # print(f"This is the data: {data}")
        documents = data['documents']
        return documents
    except Exception as e:
        print(f"This the error that caused the failed download {e}")


def get_rm_page_data():
    container_client = ContainerClient.from_connection_string(
        conn_str=os.getenv("BLOB_CONNECTION_STRING"),
        container_name=os.getenv("BLOB_CONTAINER_NAME"),
        retry_policy=ExponentialRetry(initial_backoff=2, retry_total=5)
    )

    with requests.Session() as session:
        for index, row in ccs_frameworks.iterrows():
            frame_work = row["rm_number"]
            print(f"position:{index} frame_work:{frame_work}")
            documents = agreement_docs(frame_work)

            if not documents:
                continue

            # Create a specific folder for this RM to keep it clean
            rm_temp_dir = Path.cwd() / "unzipped_data"
            rm_temp_dir.mkdir(parents=True, exist_ok=True)

            for doc in documents:
                try:
                    data_url = doc["url"]
                    # print(data_url)
                    # Use session for speed
                    response = session.get(data_url, stream=True)

                    # zip_checker needs to be careful not to exhaust RAM
                    is_zip = zip_checker(data_url, response)
                    blob_metadata = {
                        "rm_number": frame_work
                    }

                    if not is_zip:
                        # only allow  pdfs, docs and txt
                        if Path(data_url).suffix in allowed_filetypes:
                            original_name = Path(data_url).name

                            azure_file_name = original_name if frame_work in original_name else f"{frame_work}_{original_name}"

                            blob_client = container_client.get_blob_client(azure_file_name)
                            blob_client.upload_blob(data=response.content, overwrite=True, metadata=blob_metadata)


                    else:
                        # Pass the specific temp dir to unzipper
                        data_to_unzip = unzipper_v2(response, frame_work)
                        for unzipped_file in data_to_unzip:

                            blob_client = container_client.get_blob_client(unzipped_file.name)
                            with open(unzipped_file, "rb") as file:
                                blob_client.upload_blob(data=file, overwrite=True, metadata=blob_metadata)

                except Exception as e:
                    print(f"Error processing {doc.get('title')}: {e}")
                    time.sleep(1)

            # Cleanup AFTER all documents for this RM are done
            if rm_temp_dir.exists():
                shutil.rmtree(rm_temp_dir)



start_time = time.perf_counter()
get_rm_page_data()

end_time = time.perf_counter()
duration = end_time - start_time

print(f"get_rm_page_data executed in {duration:.4f} seconds")