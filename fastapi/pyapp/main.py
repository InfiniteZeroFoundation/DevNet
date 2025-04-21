from fastapi import FastAPI
from api.router import router as contracts_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# If your React app is on http://localhost:3000, allow that origin:
origins = [
    "http://localhost:3000",  # your local React
    # add other origins if needed
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the router
app.include_router(contracts_router)

# Example root route
@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI backend!"}
