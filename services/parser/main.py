from pathlib import Path
import sys
from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

# Reuse parser-service router so local command
# `uvicorn services.parser.main:app --port 8001 --reload`
# serves the same `/parse` endpoint as docker parser.
REPO_ROOT = Path(__file__).resolve().parents[2]
PARSER_SERVICE_ROOT = REPO_ROOT / "parser-service"
if str(PARSER_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(PARSER_SERVICE_ROOT))

from app.parser_router import router as parser_router

app = FastAPI(
    title="NetGuard Parser Service",
    description="Parses Terraform (.tf) and Kubernetes (.yaml) IaC files into a normalized resource representation",
    version="0.1.0",
)

app.include_router(parser_router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "parser"}
