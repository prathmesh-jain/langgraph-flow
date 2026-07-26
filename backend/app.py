from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from graph.routers import router


app = FastAPI(title="LangGraph Flow Visualization API")

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include demo routes
app.include_router(router)


@app.get("/")
async def root():
    return {"message": "LangGraph Flow Visualization API"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
