import os

import requests
from rich import console

console = console.Console()

from dincli.cli.log import logger
from dincli.cli.utils import resolve_ipfs_config

ipfs_api_url_add, ipfs_api_url_retrieve = resolve_ipfs_config()



def upload_to_ipfs(file_path, msg=None):
    with open(file_path, 'rb') as f:
        file_content = f.read()
        response = requests.post(ipfs_api_url_add, files={'file': file_content})
        if response.status_code == 200:
            if msg:
                logger.info(f"{msg} with path: {file_path} uploaded to IPFS [{response.status_code}]")
            return response.json()['Hash']
        else:
            raise Exception(f"Failed to upload file to IPFS: {response.text} and Status code: [{response.status_code}]")

def retrieve_from_ipfs(hash_value, retrieved_file_path):
    logger.info(f"Retrieving file from IPFS: {hash_value}")
    retrieve_response = requests.post(ipfs_api_url_retrieve + hash_value, stream=True)
    os.makedirs(os.path.dirname(retrieved_file_path), exist_ok=True)
    
    if retrieve_response.status_code == 200:
        with open(retrieved_file_path, 'wb') as outfile:
            for chunk in retrieve_response.iter_content(chunk_size=8192):
                outfile.write(chunk)
        logger.info(f"File retrieved and saved to: {retrieved_file_path}")
        return retrieve_response.status_code
    else:
        logger.error(f"Error retrieving file: {retrieve_response.status_code}")
        logger.error(retrieve_response.text)

    return retrieve_response.status_code