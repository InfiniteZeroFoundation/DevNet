from dincli.services.ipfs import upload_to_ipfs
import requests
from dincli.services.cid_utils import get_bytes32_from_cid, get_cidv1base32_from_cid
from pathlib import Path
from urllib.parse import quote

IPFS_API_URL_ADD="http://127.0.0.1:5001/api/v0/add?cid-version=1&pin=true&raw-leaves=true"
IPFS_API_URL_RETRIEVE="http://127.0.0.1:5001/api/v0/cat/"

def _normalize_path(path: str) -> Path:
    return Path(path).resolve()

if __name__ == "__main__":


    # manifestpath = "/home/azureuser/projects/DINv1MVC/tasks/local/0x1e315573CE1b0A7c0De6d55f5A4858c98454b133/manifest.json"
    # manifestCID = upload_to_ipfs(str(manifestpath), "manifest")
    # print("manifestCID: ", manifestCID)
    # bytes32CID = get_bytes32_from_cid(manifestCID)
    # print("bytes32CID: ", bytes32CID)

    # manifestCIDv0 = "QmWvssDTW1YpQjaVi6eZoMUuAUTxmKhkxKR1suJ4FNYWee"
    # manifestCIDv1base32 = get_cidv1base32_from_cid(manifestCIDv0)
    # print("manifestCIDv1base32: ", manifestCIDv1base32)

    # file_path = _normalize_path("/home/azureuser/projects/DINv1MVC/scripts/ipfs_upload.py")

    # with open(file_path, 'rb') as f:
    #     file_content = f.read()

    # response = requests.post(
    #     IPFS_API_URL_ADD,
    #     files={'file': (file_path.name, file_content)},
    #     timeout=30
    # )
    # response.raise_for_status()
    # cid = response.json()['Hash']
    # print("CID: ", cid)

    file_path = _normalize_path("/home/azureuser/projects/DINv1MVC/scripts/retrieved_ipfs_upload.py")

    parent = file_path.parent
    parent.mkdir(parents=True, exist_ok=True)


    hash_value = "bafkreiesnyry3hddfrp5rt55hrcrmpn6t7mn64prtl7pwdfam6e5coomky"

    response = requests.post(
                f"{IPFS_API_URL_RETRIEVE.rstrip('/')}/{quote(hash_value)}",
                stream=True,
                timeout=30
            )

    response.raise_for_status()
        
    with open(file_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
        
    
    

