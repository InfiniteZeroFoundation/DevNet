from fastapi import APIRouter, Depends, Request
from dotenv import load_dotenv, set_key, unset_key, dotenv_values
router = APIRouter(tags=["Miscellaneous"])

import httpx
from typing import List, Tuple, Optional, Dict, Any
from services.dataset_service import load_mnist_dataset, save_datasets
from services.partition_service import partition_dataset, save_partitioned_data
import time

from services.model_architect import get_DINTaskCoordinator_Instance, GIstateToDes, GIstateToStr

@router.get("/getGIState")
def get_GIState():
    try:
        env_config = dotenv_values(".env")
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        print("getting GI state")
        if DINTaskCoordinator_Contract_Address is None:
            return {"message": "DINTaskCoordinator_Contract_Address not found",
                    "status": "error",
                    "GI": 0,
                    "GIstatestr": "DINTaskCoordinator contract not deployed",
                    "GIstatedes": "DINTaskCoordinator contract not deployed"}
        else:
            
            deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
            
            GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
            
            GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
            
            GIstatedes = GIstateToDes(GIstate)
            GIstatestr = GIstateToStr(GIstate)
            
            return {"message": "GI state fetched successfully",
                    "status": "success",
                    "GI": GI,
                    "GIstate": GIstate,
                    "GIstatestr": GIstatestr,
                    "GIstatedes": GIstatedes}
    except Exception as e:
        return {"message": str(e),
                "status": "error",
                "GI": None,
                "GIstate": None,
                "GIstatestr": None,
                "GIstatedes": None}


@router.get("/distribute/dataset")
def distribute_dataset():
    num_clients = 9
    try:
        
        print("distributing dataset in misc routes")
        
        # Step 1: Load the dataset
        train_dataset, test_dataset = load_mnist_dataset()

        # Step 2: Save the datasets to disk
        save_datasets(train_dataset, test_dataset, output_dir="./Dataset")
        
        # Step 3: Partition the dataset
        partitioned_data = partition_dataset(train_dataset, num_clients)
        
        # Step 4: Save the partitioned data
        save_partitioned_data(partitioned_data, output_dir="./Dataset/clients")
        
        return {"message": "Dataset distributed successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}


@router.get("/reset/resetall")
def resetall():
    try:
        unset_key(".env", "DINCoordinator_Contract_Address")
        unset_key(".env", "DINToken_Contract_Address")
        unset_key(".env", "TaskCoordinator_Contract_Address")
        unset_key(".env", "IS_GenesisModelCreated")
        unset_key(".env", "GenesisModelIpfsHash")
        unset_key(".env", "ClientModelsCreatedF")
        unset_key(".env", "DINTaskCoordinator_Contract_Address")
        unset_key(".env", "ModelOwner_Address")
        unset_key(".env", "DINValidatorStake_Contract_Address")
        unset_key(".env", "DINCoordinator_DINValidatorStake_Contract_Address")
        unset_key(".env", "DPModeUsed")
        unset_key(".env", "DINTaskCoordinatorISslasher")
        unset_key(".env", "TetherMock_Contract_Address")
        unset_key(".env", "DINTaskAuditor_Contract_Address")
        unset_key(".env", "DINTaskAuditorISslasher")
        
        
        
        
        return {"message": "ALL Reset successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}

@router.get("/test")
def test():
    return {"message": "Router is working!"}



# Order matters. Add the rest of your steps here.
ONE_CLICK_STEPS: List[Tuple[str, str, Optional[dict]]] = [
    ("GET",  "/reset/resetall",                               None),
    ("POST", "/tetherfoundation/deployTetherMockContract",    None),
    ("POST", "/dindao/deployDINCoordinator",                  None),
    ("POST", "/dindao/deployDinValidatorStake",               None),
    ("POST", "/modelowner/buyUSDT",                           None),
    ("POST", "/modelowner/deployDINTaskCoordinator",          None),
    ("POST", "/modelowner/deployDINtaskAuditor",              None),
    ("POST", "/modelowner/depositRewardInDINtaskAuditor",            None),
    ("POST", "/dindao/addDINTaskCoordinatorAsSlasher",            None),
    ("POST", "/modelowner/setDINTaskCoordinatorAsSlasher",            None),
    ("POST", "/dindao/addDINTaskAuditorAsSlasher",            None),
    ("POST", "/modelowner/setDINTaskAuditorAsSlasher",            None),
    ("POST", "/modelowner/createGenesisModel",            None),
    ("POST", "/modelowner/startGI",            None),
    ("POST", "/modelowner/startDINvalidatorRegistration",            None),
    ("POST", "/validators/buyDINTokens",            None),
    ("POST", "/validators/stakeDINTokens",            None),
    ("POST", "/validators/registerTaskValidators",            None),
    ("POST", "/modelowner/closeDINvalidatorRegistration",            None),
    ("POST", "/modelowner/startDINauditorRegistration",            None),
    ("POST", "/auditors/buyDINTokens",            None),
    ("POST", "/auditors/stakeDINTokens",            None),
    ("POST", "/auditors/registerTaskAuditors",            None),
    ("POST", "/modelowner/closeDINauditorRegistration",            None),
    ("POST", "/modelowner/startLMsubmissions",            None),
    ("POST", "/clients/createClientModels",            {"selectedDPMode": "afterTraining"}),
    ("POST", "/modelowner/closeLMsubmissions",            None),
    ("POST", "/modelowner/createAuditorsBatches", None),
    ("POST", "/modelowner/createTestSubDatasetsForAuditorsBatches", None),
    ("POST", "/modelowner/startLMsubmissionsEvaluation",            None)
]


@router.get("/oneclicksetup")
async def oneclicksetup(
    request: Request,
    stop_on_error: bool = True,
    timeout_seconds: float = 60.0,
):
    """Run a stack of your existing routes in sequence, in-process."""
    transport = httpx.ASGITransport(app=request.app)
    results: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://app",  # required placeholder
        timeout=timeout_seconds,
    ) as client:
        for method, path, payload in ONE_CLICK_STEPS:
            try:
                resp = await client.request(method, path, json=payload)
                try:
                    body = resp.json()
                except Exception:
                    body = resp.text

                results.append({
                    "method": method,
                    "path": path,
                    "status": resp.status_code,
                    "ok": resp.is_success,
                    "response": body,
                })
                
                time.sleep(2)

                if not resp.is_success and stop_on_error:
                    return {
                        "ok": False,
                        "message": "One click setup halted on error.",
                        "failed_at": path,
                        "results": results,
                    }
            except Exception as e:
                results.append({"method": method, "path": path, "ok": False, "error": str(e)})
                if stop_on_error:
                    return {
                        "ok": False,
                        "message": "One click setup halted on exception.",
                        "failed_at": path,
                        "results": results,
                    }

    return {"ok": True, "message": "One click setup completed!", "results": results}