from fastapi import APIRouter, Depends
from pydantic import BaseModel
from dotenv import load_dotenv, set_key, unset_key, dotenv_values

from services.model_architect import get_DINTaskCoordinator_Instance, get_DINTaskAuditor_Instance

router = APIRouter(prefix="/globalanalytics", tags=["Global Analytics"])


@router.post("/getGlobalAnalyticsState")
def get_globalanalytics_state():
    
    env_config = dotenv_values(".env")
    
    model_owner_address = env_config.get("ModelOwner_Address")
    
    DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
    
    DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
    
    if DINTaskCoordinator_Contract_Address is None or DINTaskAuditor_Contract_Address is None:
        return {"message": "DIN Task Coordinator or Task Auditor Not deployed",
            "status": "error"}
      
    deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    
    deployed_DINTaskAuditorContract = get_DINTaskAuditor_Instance(dintaskauditor_address=DINTaskAuditor_Contract_Address)
    print("Current GI:", curr_GI)
    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
    print("Current GIstate:", GIstate)
    GIaccuracy = []
    

    if curr_GI > 0:
        # All GIs from 0 to curr_GI - 1 are complete and have scores available
        # Only include current GI (== curr_GI) if GIstate >= 19
        max_GI_to_fetch = curr_GI  # GI=0,1,...,curr_GI-1 → total = curr_GI values

        if GIstate >= 19:
            # Current GI is also complete — include it too
            max_GI_to_fetch = curr_GI + 1

        # Fetch all completed GIs
        for GI in range(max_GI_to_fetch):
            try:
                score = deployed_DINTaskCoordinatorContract.functions.getTier2Score(GI).call()
                GIaccuracy.append(score)
            except Exception as e:
                print(f"Failed to fetch score for GI {GI}: {e}")
                GIaccuracy.append(None)  # or skip, depending on your needs

    elif curr_GI == 0 and GIstate >= 4:
        # Genesis GI (GI=0) score available at state 4
        score = deployed_DINTaskCoordinatorContract.functions.getTier2Score(0).call()
        GIaccuracy.append(score)

    return {"message": "Global Analytics State fetched successfully",
            "status": "success",
            "GIaccuracy": GIaccuracy}
