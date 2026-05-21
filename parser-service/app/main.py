from fastapi import FastAPI
from .parser_router import router

app = FastAPI()

@app.get("/")
def root():
    return {"message": "NetGuard Parser Service Running"}

app.include_router(router)