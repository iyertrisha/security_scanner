from fastapi import APIRouter, HTTPException, UploadFile
from .terraform_parser import parse_terraform, parse_module_sources
from .kubernetes_parser import parse_kubernetes
from .schema import ParseResponse

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "service": "parser"}


@router.post("/parse")
async def parse_file(file: UploadFile) -> ParseResponse:
    filename = file.filename or "unknown"
    try:
        content = (await file.read()).decode()

        if filename.endswith(".tf"):
            resources = parse_terraform(content, source_file=filename)
            module_sources = parse_module_sources(content)
            return ParseResponse(resources=resources, module_sources=module_sources)

        if filename.endswith(".yaml") or filename.endswith(".yml"):
            resources = parse_kubernetes(content, source_file=filename)
            return ParseResponse(resources=resources, module_sources=[])
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unable to parse IaC file",
                "filename": filename,
                "error": str(exc),
            },
        ) from exc

    return ParseResponse(resources=[], module_sources=[])