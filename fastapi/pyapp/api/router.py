from fastapi import APIRouter

from .modelowner_routes import router as modelowner_router
from .validator_routes import router as validator_router
from .client_routes import router as client_router
from .dindao_routes import router as dindao_router
from .misc_routes import router as misc_router
from .tetherfoundation_routes import router as tetherfoundation_router
from .auditors_routes import router as auditors_router
from .globalanalytics_routes import router as globalanalytics_router

router = APIRouter()

router.include_router(modelowner_router)
router.include_router(validator_router)
router.include_router(client_router)
router.include_router(dindao_router)
router.include_router(misc_router)
router.include_router(auditors_router)
router.include_router(tetherfoundation_router)
router.include_router(globalanalytics_router)


