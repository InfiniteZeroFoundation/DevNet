
import requests
import string
import random
import os

ipfs_api_url_add = 'http://127.0.0.1:5001/api/v0/add'
ipfs_api_url_retrieve = 'http://127.0.0.1:5001/api/v0/cat?arg='


def upload_to_ipfs(file_path, msg=None):
    with open(file_path, 'rb') as f:
        file_content = f.read()
        response = requests.post(ipfs_api_url_add, files={'file': file_content})
        if response.status_code == 200:
            if msg:
                print(msg," with path: ",file_path," uploaded to IPFS [",response.status_code,"]")
            return response.json()['Hash']
        else:
            raise Exception(f"Failed to upload file to IPFS: {response.text} and Status code: [{response.status_code}]")

def retrieve_from_ipfs(hash_value, retrieved_file_path):
    retrieve_response = requests.post(ipfs_api_url_retrieve + hash_value, stream=True)
    os.makedirs(os.path.dirname(retrieved_file_path), exist_ok=True)
    
    if retrieve_response.status_code == 200:
        with open(retrieved_file_path, 'wb') as outfile:
            for chunk in retrieve_response.iter_content(chunk_size=8192):
                outfile.write(chunk)
        print(f"File retrieved and saved to: {retrieved_file_path}")
        return retrieve_response.status_code
    else:
        print(f"Error retrieving file: {retrieve_response.status_code}")
        print(retrieve_response.text)

    return retrieve_response.status_code

def generate_fake_cid_v0(length=44):
    # IPFS CID v0 starts with 'Qm', then 44 more chars from [A-Za-z2-9]
    prefix = 'Qm'
    chars = string.ascii_letters + '123456789'  # base58-like characters
    random_str = ''.join(random.choices(chars, k=length))
    return prefix + random_str