# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Naveen

"""Optional loopback-only HTTP service."""

import argparse
import tempfile
from pathlib import Path

from .errors import LocalRedactError
from .service import redact

SOURCE_URL = "https://github.com/1aifanatic/localredact"


def create_app(*, max_upload_mb: int = 50):
    """Create the optional FastAPI application without importing it in the core."""

    try:
        from fastapi import FastAPI, File, Form, HTTPException, UploadFile
        from fastapi.background import BackgroundTasks
        from fastapi.responses import FileResponse
    except ImportError as error:
        raise RuntimeError(
            "The server extra is not installed. Run: python -m pip install 'localredact[server]'"
        ) from error

    app = FastAPI(
        title="LocalRedact",
        version="0.1.0",
        description="Loopback-first local PDF redaction. No outbound document transfer.",
        contact={"name": "LocalRedact maintainers", "url": f"{SOURCE_URL}/issues"},
        license_info={"name": "AGPL-3.0-only", "identifier": "AGPL-3.0-only"},
    )
    byte_limit = max_upload_mb * 1024 * 1024

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {"status": "ok", "local_processing": True}

    @app.get("/v1/about")
    async def about() -> dict[str, str]:
        return {
            "name": "LocalRedact",
            "license": "AGPL-3.0-only",
            "source": SOURCE_URL,
            "warranty": "This software is provided without warranty.",
        }

    @app.post("/v1/redact", response_class=FileResponse)
    async def redact_endpoint(
        background_tasks: BackgroundTasks,
        document: UploadFile = File(...),
        instruction: str = Form(...),
        ocr: bool = Form(False),
        ocr_language: str = Form("eng"),
    ):
        workspace = tempfile.TemporaryDirectory(prefix="localredact-")
        source = Path(workspace.name) / "input.pdf"
        output = Path(workspace.name) / "redacted.pdf"
        size = 0
        try:
            with source.open("wb") as stream:
                while chunk := await document.read(1024 * 1024):
                    size += len(chunk)
                    if size > byte_limit:
                        raise HTTPException(
                            413, f"PDF exceeds the {max_upload_mb} MB upload limit."
                        )
                    stream.write(chunk)
            result = redact(
                source,
                instruction,
                output,
                ocr=ocr,
                ocr_language=ocr_language,
                max_file_size=byte_limit,
            )
        except HTTPException:
            workspace.cleanup()
            raise
        except LocalRedactError as error:
            workspace.cleanup()
            raise HTTPException(422, str(error)) from error
        except Exception:
            workspace.cleanup()
            raise
        finally:
            await document.close()

        background_tasks.add_task(workspace.cleanup)
        categories = ",".join(result.category_counts)
        return FileResponse(
            output,
            media_type="application/pdf",
            filename="redacted.pdf",
            headers={
                "X-Redaction-Count": str(result.redaction_count),
                "X-Redaction-Categories": categories,
                "Cache-Control": "no-store",
            },
            background=background_tasks,
        )

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="localredact-server",
        description="Run the optional local PDF redaction service.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--max-upload-mb", type=int, default=50)
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="allow a non-loopback bind (requires you to provide network security)",
    )
    arguments = parser.parse_args(argv)
    loopback = {"127.0.0.1", "::1", "localhost"}
    if arguments.host not in loopback and not arguments.allow_network:
        parser.error("non-loopback binding requires --allow-network")
    if not 1 <= arguments.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if not 1 <= arguments.max_upload_mb <= 1024:
        parser.error("--max-upload-mb must be between 1 and 1024")
    try:
        import uvicorn
    except ImportError as error:
        parser.error(
            "the server extra is not installed; run: python -m pip install 'localredact[server]'"
        )
        raise AssertionError from error
    uvicorn.run(
        create_app(max_upload_mb=arguments.max_upload_mb),
        host=arguments.host,
        port=arguments.port,
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
