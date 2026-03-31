import io
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

import pandas as pd
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import models
from .certificate_generator import (
    GENERATED_DIR,
    LAYOUT_PATH,
    TEMPLATE_CONFIG_PATH,
    TEMPLATE_PATH,
    generate_certificate,
    load_layout,
    render_certificate_pdf_bytes,
    save_layout,
)
from .database import PROJECT_ROOT, get_db, init_db  # type: ignore[attr-defined]
from .email_service import send_certificate_email


# Load environment variables from .env at project root
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

# Create database tables + apply lightweight migrations
init_db()

# Ensure runtime directories exist (for local runs and deployment)
PROJECT_ROOT.joinpath("templates").mkdir(parents=True, exist_ok=True)
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Certificate Generation & Email Sending System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve built frontend assets (Vite build outputs to app/static)
static_root = PROJECT_ROOT / "app" / "static"
index_path = static_root / "index.html"
assets_dir = static_root / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


def _serve_app() -> FileResponse:
    """Serve the SPA index.html; used by /, /setup, /editor."""
    if not index_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend not built. Run: cd frontend && npm install && npm run build",
        )
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    return FileResponse(index_path, headers=headers)


@app.get("/")
def ui_home() -> FileResponse:
    return _serve_app()


@app.get("/setup")
def ui_setup() -> FileResponse:
    return _serve_app()


@app.get("/editor")
def ui_editor() -> FileResponse:
    return _serve_app()


@app.get("/upload")
def ui_upload() -> FileResponse:
    return _serve_app()


@app.get("/participants")
def ui_participants() -> FileResponse:
    return _serve_app()


@app.get("/email-queue")
def ui_email_queue() -> FileResponse:
    return _serve_app()


@app.get("/certificates")
def ui_certificates() -> FileResponse:
    return _serve_app()


@app.get("/settings")
def ui_settings() -> FileResponse:
    return _serve_app()


@app.get("/template-preview")
def template_preview() -> Response:
    headers = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
    if not TEMPLATE_PATH.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    return FileResponse(TEMPLATE_PATH, headers=headers)

@app.delete("/template")
def delete_template() -> Dict[str, Any]:
    if TEMPLATE_PATH.exists():
        TEMPLATE_PATH.unlink()
    return {"status": "ok", "template_set": False}


@app.post("/upload-template")
def upload_template(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Upload a new PNG template for certificates and save it as templates/certificate.png.
    """
    if not file.filename.lower().endswith((".png", ".jpg", ".jpeg")):
        raise HTTPException(status_code=400, detail="Template must be a PNG or JPEG image.")

    PROJECT_ROOT.joinpath("templates").mkdir(parents=True, exist_ok=True)

    content = file.file.read()
    # Always store as PNG filename; content type is not enforced beyond extension check
    TEMPLATE_PATH.write_bytes(content)

    return {"status": "ok", "template_path": str(TEMPLATE_PATH)}

@app.get("/template-config")
def get_template_config() -> Dict[str, Any]:
    if not TEMPLATE_CONFIG_PATH.exists():
        return {
            "x_ratio": 0.5,
            "y_ratio": 0.5,
            "font_size": 32,
            "color": "#000000",
            "sample_name": "John Doe",
        }
    try:
        data = json.loads(TEMPLATE_CONFIG_PATH.read_text(encoding="utf-8"))
        return data
    except Exception:
        return {
            "x_ratio": 0.5,
            "y_ratio": 0.5,
            "font_size": 32,
            "color": "#000000",
            "sample_name": "John Doe",
        }


@app.post("/template-config")
def save_template_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Keep it simple: accept JSON dict with keys x_ratio, y_ratio, font_size, color
    data = {
        "x_ratio": float(payload.get("x_ratio", 0.5)),
        "y_ratio": float(payload.get("y_ratio", 0.5)),
        "font_size": int(payload.get("font_size", 32)),
        "color": str(payload.get("color", "#000000")),
        "sample_name": str(payload.get("sample_name", "Laukik Rathod")),
    }
    import json as _json

    TEMPLATE_CONFIG_PATH.write_text(_json.dumps(data, indent=2), encoding="utf-8")
    return {"status": "ok", "config": data}

# Pydantic models for layout configuration and live preview
class LayoutConfig(BaseModel):
    name_x: float = 297.5
    name_y: float = 421.0
    font_size: int = 32
    font_family: str = "Sans"
    color: str = "#000000"
    max_width: int = 500

class PreviewLiveRequest(BaseModel):
    name: str = "John Doe"
    layout: LayoutConfig


class SendEmailsRequest(BaseModel):
    subject: str = None
    message_body: str = None

@app.get("/layout")
def get_layout() -> Dict[str, Any]:
    # Ensure we always return a usable layout, even if layout.json is missing/corrupt
    return load_layout()


@app.post("/layout")
def post_layout(payload: Dict[str, Any], db: Session = Depends(get_db)) -> Dict[str, Any]:
    saved = save_layout(payload)
    
    # Regenerate all existing participants with the new layout
    participants = db.query(models.Participant).all()
    print(f"DEBUG: Regenerating {len(participants)} certificates for new layout: {saved}")
    if getattr(db, 'is_active', True): # Ensure db session is fine
        for p in participants:
            try:
                pdf_path = generate_certificate(name=p.name, email=p.email, display_name=p.display_name)
                p.certificate_file = os.path.basename(pdf_path)
                db.add(p)
            except Exception as e:
                print(f"DEBUG Error regenerating for {p.email}: {e}")
                pass
        db.commit()
    print("DEBUG: Layout and PDF regeneration finished.")

    return {"status": "ok", "layout": saved, "path": str(LAYOUT_PATH)}


@app.get("/preview")
def preview(name: str) -> Response:
    """
    Generate a preview certificate PDF for a given name using SAVED layout.
    """
    n = (name or "").strip()
    if not n:
        raise HTTPException(status_code=400, detail="Query param 'name' is required.")

    pdf_bytes = render_certificate_pdf_bytes(name=n) # Updated to pass name as keyword arg
    return Response(content=pdf_bytes, media_type="application/pdf")


@app.post("/preview-live")
def preview_live(request: PreviewLiveRequest) -> Response: # Updated to use PreviewLiveRequest
    """
    Generate a preview certificate PDF using PROVIDED layout (unsaved state).
    """
    name = request.name.strip()
    layout_dict = request.layout.model_dump() # Convert Pydantic model to dict
    if not layout_dict:
        raise HTTPException(status_code=400, detail="Layout data is required")

    pdf_bytes = render_certificate_pdf_bytes(name=name, layout=layout_dict) # Updated to pass name and layout as keyword args
    return Response(content=pdf_bytes, media_type="application/pdf")


@app.get("/download-certificates")
def download_certificates() -> Response:
    """
    Download a ZIP archive of all generated PDFs in generated/.
    """
    import zipfile

    if not GENERATED_DIR.exists():
        raise HTTPException(status_code=404, detail="No generated folder found.")

    pdfs = sorted([p for p in GENERATED_DIR.glob("*.pdf") if p.is_file()])
    if not pdfs:
        raise HTTPException(status_code=404, detail="No generated PDF certificates found.")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in pdfs:
            zf.write(p, arcname=p.name)
    zip_bytes = buf.getvalue()

    headers = {
        "Content-Disposition": 'attachment; filename="certificates.zip"'
    }
    return Response(content=zip_bytes, media_type="application/zip", headers=headers)


@app.get("/generated/{filename}")
def download_generated_file(filename: str) -> FileResponse:
    safe = os.path.basename(filename)
    path = GENERATED_DIR / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path, media_type="application/pdf", filename=safe)

@app.get("/health")
def api_health() -> Dict[str, Any]:
    sender_email = os.getenv("SENDER_EMAIL")
    app_password = os.getenv("APP_PASSWORD")
    credentials_ok = bool(sender_email and app_password)
    template_set = TEMPLATE_PATH.exists()
    return {
        "status": "ok",
        "template_set": template_set,
        "credentials_ok": credentials_ok,
    }

@app.get("/status")
def get_status(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    participants = (
        db.query(models.Participant)
        .order_by(models.Participant.created_at.desc())
        .all()
    )
    result: List[Dict[str, Any]] = []
    for p in participants:
        result.append(
            {
                "id": p.id,
                "name": p.name,
                "display_name": p.display_name,
                "email": p.email,
                "status": p.status,
                "error_message": p.error_message,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "last_sent_at": p.last_sent_at.isoformat() if p.last_sent_at else None,
                "attempts": p.attempts,
                "certificate_file": p.certificate_file,
            }
        )
    return result


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize DataFrame column names: strip BOM, whitespace, quotes, lowercase."""
    BOM = chr(0xFEFF)
    mapping: Dict[str, str] = {}
    for col in df.columns:
        key = str(col).strip().lstrip(BOM).strip()
        key = key.replace('"', '').replace("'", '').lower()
        if key == 'display name':
            key = 'display_name'
        mapping[col] = key
    df = df.rename(columns=mapping)
    return df


def _process_upload(file: UploadFile, db: Session) -> Dict[str, Any]:
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    try:
        file.file.seek(0)
        df = pd.read_csv(file.file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read CSV file: {e}")

    df = _normalize_columns(df)
    if "name" not in df.columns or "email" not in df.columns:
        found_cols = ", ".join(str(c) for c in df.columns)
        raise HTTPException(
            status_code=400,
            detail=f"CSV must contain 'Name' and 'Email' columns. Found columns: [{found_cols}]",
        )

    total = len(df)
    sent = 0
    failed = 0
    skipped = 0

    for row in df.itertuples(index=False):
        name = str(getattr(row, "name", "")).strip()
        email = str(getattr(row, "email", "")).strip()
        display_name = ""
        if hasattr(row, "display_name"):
            display_name = str(getattr(row, "display_name") or "").strip()
        if not display_name:
            display_name = name

        participant = None

        if not name or not email or email.lower() == "nan":
            failed += 1
            continue

        try:
            participant = models.Participant(
                name=name,
                display_name=display_name,
                email=email,
                status="pending",
                certificate_file=None,
            )
            db.add(participant)
            db.commit()
            db.refresh(participant)
            sent += 1

        except Exception as e:
            db.rollback()
            try:
                error_text = str(e)
                failed_participant = models.Participant(
                    name=name or "",
                    display_name=display_name or (name or ""),
                    email=email or "",
                    status="failed",
                    error_message=error_text,
                    certificate_file=None,
                    attempts=0,
                )
                db.add(failed_participant)
                db.commit()
            except Exception:
                db.rollback()
            failed += 1

    return {
        "summary": {
            "total": int(total),
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
        }
    }


@app.post("/generate-certificates")
def generate_certificates(file: UploadFile = File(...), db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Import CSV into the database for processing using pandas to_sql to ensure clean appending.
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    try:
        file.file.seek(0)
        df = pd.read_csv(file.file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read CSV file: {e}")

    df = _normalize_columns(df)
    if "name" not in df.columns or "email" not in df.columns:
        raise HTTPException(status_code=400, detail="CSV must contain 'Name' and 'Email' columns.")

    # Drop empty names/emails
    df["name"] = df["name"].astype(str).str.strip()
    df["email"] = df["email"].astype(str).str.strip()
    df = df[df["name"].astype(bool) & df["email"].astype(bool) & (df["email"].str.lower() != "nan")]

    if "display_name" not in df.columns:
        df["display_name"] = df["name"]
    else:
        df["display_name"] = df["display_name"].astype(str).str.strip()
        df["display_name"] = df["display_name"].replace("", pd.NA).fillna(df["name"])

    df["status"] = "pending"
    df["attempts"] = 0
    df["created_at"] = datetime.utcnow()
    df["last_sent_at"] = None
    df["certificate_file"] = None
    df["error_message"] = None

    print(f"Rows received: {len(df)}")
    print("Appending to database...")

    from .database import engine

    cols = ["name", "email", "display_name", "status", "attempts", "created_at", "last_sent_at", "certificate_file", "error_message"]
    df_to_insert = df[[c for c in cols if c in df.columns]]

    processed_count = len(df_to_insert)
    failed = 0

    try:
        with engine.begin() as conn:
            df_to_insert.to_sql("participants", conn, if_exists="append", index=False)
    except Exception as e:
        print(f"DEBUG Error to_sql: {e}")
        processed_count = 0
        failed = len(df_to_insert)

    return {
        "summary": {
            "total": int(len(df)),
            "processed": int(processed_count),
            "failed": failed,
            "skipped": 0,
        }
    }


@app.post("/upload")
def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)) -> Dict[str, Any]:
    return _process_upload(file, db)


@app.post("/retry-failed")
def retry_failed(payload: SendEmailsRequest = None, db: Session = Depends(get_db)) -> Dict[str, Any]:
    failed_participants = (
        db.query(models.Participant)
        .filter(models.Participant.status == "failed")
        .all()
    )

    total = len(failed_participants)
    sent = 0
    still_failed = 0

    for participant in failed_participants:
        name = participant.name
        display_name = participant.display_name or participant.name
        email = participant.email

        try:
            pdf_path = generate_certificate(name=name, email=email, display_name=display_name)

            send_certificate_email(
                display_name=display_name,
                recipient_email=email,
                pdf_path=pdf_path,
                certificate_name=name,
                subject=payload.subject if payload else None,
                message_body=payload.message_body if payload else None,
            )

            participant.status = "sent"
            participant.error_message = None
            participant.last_sent_at = datetime.utcnow()
            participant.attempts = (participant.attempts or 0) + 1

            attempt = models.SendAttempt(
                participant_id=participant.id,
                status="sent",
                error_message=None,
            )
            db.add(attempt)
            db.commit()
            generated += 1

            time.sleep(2)
        except Exception as e:
            db.rollback()
            try:
                error_text = str(e)
                participant.status = "failed"
                participant.error_message = error_text
                participant.last_sent_at = datetime.utcnow()
                participant.attempts = (participant.attempts or 0) + 1
                db.add(participant)

                attempt = models.SendAttempt(
                    participant_id=participant.id,
                    status="failed",
                    error_message=error_text,
                )
                db.add(attempt)
                db.commit()
            except Exception:
                db.rollback()
            still_failed += 1

    return {
        "summary": {
            "total_failed_before": total,
            "resent_successfully": sent,
            "still_failed": still_failed,
        }
    }


@app.post("/generate-pending")
def generate_pending(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Generate PDFs for all participants with status='pending' and certificate_file=None.
    """
    participants = (
        db.query(models.Participant)
        .filter(models.Participant.status == "pending")
        .filter(models.Participant.certificate_file == None)
        .all()
    )
    
    total = len(participants)
    generated = 0
    failed = 0
    
    for p in participants:
        try:
            pdf_path = generate_certificate(name=p.name, email=p.email, display_name=p.display_name)
            p.certificate_file = os.path.basename(pdf_path)
            db.commit()
            generated += 1
        except Exception as e:
            db.rollback()
            p.status = "failed"
            p.error_message = str(e)
            db.commit()
            failed += 1
            
    return {
        "summary": {
            "total_pending": total,
            "generated": generated,
            "failed": failed,
        }
    }


@app.post("/send-emails")
def send_emails(payload: SendEmailsRequest = None, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Send emails for participants with status='pending'.
    Uses existing generated PDF if present; otherwise generates it.
    """
    pending_participants = (
        db.query(models.Participant)
        .filter(models.Participant.status == "pending")
        .order_by(models.Participant.created_at.asc())
        .all()
    )

    total = len(pending_participants)
    sent = 0
    failed = 0
    skipped = 0
    
    last_error = "Unknown Error"

    for participant in pending_participants:
        name = participant.name
        display_name = participant.display_name or participant.name
        email = participant.email

        try:
            # Force regeneration using the latest layout
            pdf_path = generate_certificate(name=name, email=email, display_name=display_name)
            participant.certificate_file = os.path.basename(pdf_path)

            send_certificate_email(
                display_name=display_name,
                recipient_email=email,
                pdf_path=pdf_path,
                certificate_name=name,
                subject=payload.subject if payload else None,
                message_body=payload.message_body if payload else None,
            )

            participant.status = "sent"
            participant.error_message = None
            participant.last_sent_at = datetime.utcnow()
            participant.attempts = (participant.attempts or 0) + 1

            attempt = models.SendAttempt(
                participant_id=participant.id,
                status="sent",
                error_message=None,
            )
            db.add(attempt)
            db.add(participant)
            db.commit()
            sent += 1

            time.sleep(1)

        except Exception as e:
            db.rollback()
            error_text = str(e)
            last_error = error_text
            try:
                participant.status = "failed"
                participant.error_message = error_text
                participant.last_sent_at = datetime.utcnow()
                participant.attempts = (participant.attempts or 0) + 1
                db.add(participant)

                attempt = models.SendAttempt(
                    participant_id=participant.id,
                    status="failed",
                    error_message=error_text,
                )
                db.add(attempt)
                db.commit()
            except Exception:
                db.rollback()
            failed += 1

    return {
        "summary": {
            "total_pending_before": total,
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
            "last_error": last_error if failed > 0 else None
        }
    }


@app.delete("/participants")
def delete_participants(db: Session = Depends(get_db)) -> Dict[str, Any]:
    db.query(models.SendAttempt).delete()
    db.query(models.Participant).delete()
    db.commit()
    # Explicitly clear file cache
    if GENERATED_DIR.exists():
        for f in GENERATED_DIR.iterdir():
            if f.is_file():
                try:
                    f.unlink()
                except Exception:
                    pass
    return {"status": "ok", "message": "All database records and PDF files cleared."}

@app.post("/reset-status")
def reset_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Reset all participants to 'pending' to allow re-sending."""
    db.query(models.Participant).update({"status": "pending", "error_message": None})
    db.commit()
    return {"status": "ok", "message": "All participants reset to pending"}

@app.get('/debug-info')
def debug_info(db: Session = Depends(get_db)):
    from .database import DB_PATH
    count = db.query(models.Participant).count()
    return {'db_path': str(DB_PATH).replace('\\', '/'), 'participant_count': count}
