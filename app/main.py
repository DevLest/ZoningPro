from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any, Literal

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import EXPORTS_DIR, PROJECT_ROOT
from app.db import get_db, init_db
from app.export_excel import export_lc_workbook
from app.fees import TEMPLATE_REGISTRY, compute_fees, list_categories, suggest_template
from app.fees.registry import get_template
from app.models import LCApplication
from app.pdf_slip import build_assessment_pdf
from app.resolved_fees import DisplayFees, display_fees_for_application
from app.ui_context import merge_shell, shell_for_application

PROJECT_TYPE_DISPLAY = {
    "residential": "RESIDENTIAL",
    "apartment": "APARTMENT/TOWNHOUSE",
    "dormitory": "DORMITORIES",
    "commercial": "COMM'L/INDUS./AGRO-INDUS.",
    "institutional": "INSTITUTIONAL",
    "special_use": "SPECIAL USE",
}

LC_STATUS_OPTIONS: list[tuple[str, str]] = [
    ("", "— Select status —"),
    ("Pending", "Pending"),
    ("Under review", "Under review"),
    ("Approved", "Approved"),
    ("Granted", "Granted"),
    ("Denied", "Denied"),
    ("Cancelled", "Cancelled"),
]
LC_STATUS_KNOWN = {v for v, _ in LC_STATUS_OPTIONS if v}

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))


class AssessmentSyncIn(BaseModel):
    lc_status: str | None = None
    date_granted: str | None = None
    optional_units: str | None = None
    surcharge_amount: str | None = None
    waive_zoning_cert: bool = False
    lc_fee_amount: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Zoning Assessment", version="1.0.0", lifespan=lifespan)

static_dir = PROJECT_ROOT / "app" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def _parse_date(s: str | None) -> date | None:
    if not s or not str(s).strip():
        return None
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def _parse_surcharge_override(raw: str, computed_surcharge: float) -> float | None:
    """Empty or same-as-computed clears manual override (use formula)."""
    s = (raw or "").strip()
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if abs(v - computed_surcharge) < 0.005:
        return None
    return v


def _parse_lc_fee_override(raw: str | None, computed_lc: float) -> float | None:
    """Empty or same-as-computed clears manual override (use formula)."""
    s = (raw or "").strip()
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if abs(v - computed_lc) < 0.005:
        return None
    return v


def _display_fees_dict(d: DisplayFees) -> dict[str, Any]:
    return {
        "lc_fee": d.lc_fee,
        "computed_lc_fee": d.computed_lc_fee,
        "surcharge": d.surcharge,
        "zoning_cert": d.zoning_cert,
        "total": d.total,
        "computed_surcharge": d.computed_surcharge,
        "computed_zoning_cert": d.computed_zoning_cert,
        "surcharge_overridden": d.surcharge_overridden,
        "lc_fee_overridden": d.lc_fee_overridden,
        "zoning_waived": d.zoning_waived,
    }


def _apply_assessment_inputs(
    row: LCApplication,
    *,
    lc_status: str | None,
    date_granted: str | None,
    optional_units: str | None,
    surcharge_amount: str | None,
    waive_zoning_cert: bool,
    lc_fee_amount: str | None,
    db: Session,
) -> DisplayFees:
    row.lc_status = (lc_status or "").strip() or None
    row.date_granted = _parse_date(date_granted)
    ou = (optional_units or "").strip()
    row.optional_units = float(ou) if ou else None
    base = compute_fees(
        row.template_id or "",
        float(row.project_cost or 0),
        lot_area_sqm=row.lot_area_sqm,
        optional_units=row.optional_units,
    )
    row.surcharge_override = _parse_surcharge_override(surcharge_amount or "", base.surcharge)
    row.lc_fee_override = _parse_lc_fee_override(lc_fee_amount, base.lc_fee)
    row.waive_zoning_cert = waive_zoning_cert
    db.commit()
    db.refresh(row)
    _base, display = display_fees_for_application(row)
    return display


@app.get("/api/suggest-template")
def api_suggest_template(category: str, project_cost: float):
    return {"template_id": suggest_template(category, project_cost)}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    apps = db.query(LCApplication).order_by(LCApplication.created_at.desc()).limit(100).all()
    classified_count = sum(1 for a in apps if a.template_id)
    with_totals_count = sum(1 for a in apps if a.total is not None)
    return templates.TemplateResponse(
        request,
        "index.html",
        merge_shell(
            {
                "applications": apps,
                "classified_count": classified_count,
                "with_totals_count": with_totals_count,
            },
            nav_active="dashboard",
            sidebar_active="overview",
        ),
    )


@app.get("/applications/new", response_class=HTMLResponse)
def new_application_form(request: Request):
    today = date.today().isoformat()
    return templates.TemplateResponse(
        request,
        "new.html",
        merge_shell(
            {"today": today},
            nav_active="new_application",
            sidebar_active="site_analysis",
            project_title="New LC application",
            project_subtitle="Intake form",
        ),
    )


@app.post("/applications/new")
def new_application_post(
    lc_ctrl_no: str = Form(...),
    date_of_application: str = Form(...),
    applicant_name: str = Form(...),
    address: str = Form(...),
    project_name: str = Form(""),
    project_location: str = Form(""),
    doc_requirements: str = Form(""),
    lc_status: str = Form(""),
    date_granted: str = Form(""),
    db: Session = Depends(get_db),
):
    row = LCApplication(
        lc_ctrl_no=lc_ctrl_no.strip(),
        date_of_application=_parse_date(date_of_application) or date.today(),
        applicant_name=applicant_name.strip(),
        address=address.strip(),
        project_name=project_name.strip() or None,
        project_location=project_location.strip() or None,
        doc_requirements=doc_requirements.strip() or None,
        lc_status=lc_status.strip() or None,
        date_granted=_parse_date(date_granted),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return RedirectResponse(url=f"/applications/{row.id}/classify", status_code=303)


@app.get("/applications/{app_id}/classify", response_class=HTMLResponse)
def classify_get(request: Request, app_id: int, db: Session = Depends(get_db)):
    row = db.get(LCApplication, app_id)
    if not row:
        raise HTTPException(404)
    suggested = None
    if row.category and row.project_cost is not None:
        suggested = suggest_template(row.category, row.project_cost)
    cat_labels = dict(list_categories())
    grouped = {}
    for t in TEMPLATE_REGISTRY:
        grouped.setdefault(t.category, []).append(t)
    ctx = shell_for_application(row, nav_active="estimations", sidebar_active="site_analysis")
    ctx.update(
        {
            "app": row,
            "categories": list_categories(),
            "templates": TEMPLATE_REGISTRY,
            "templates_grouped": grouped,
            "cat_labels": cat_labels,
            "suggested": suggested,
        }
    )
    return templates.TemplateResponse(request, "classify.html", ctx)


@app.post("/applications/{app_id}/classify")
def classify_post(
    app_id: int,
    category: str = Form(...),
    project_cost: float = Form(...),
    lot_area_sqm: str = Form(""),
    template_id: str = Form(...),
    db: Session = Depends(get_db),
):
    row = db.get(LCApplication, app_id)
    if not row:
        raise HTTPException(404)
    row.category = category.strip()
    row.project_cost = float(project_cost)
    la = lot_area_sqm.strip()
    row.lot_area_sqm = float(la) if la else None
    row.template_id = template_id.strip()
    db.commit()
    return RedirectResponse(url=f"/applications/{app_id}/assessment", status_code=303)


@app.get("/applications/{app_id}/assessment", response_class=HTMLResponse)
def assessment_get(request: Request, app_id: int, db: Session = Depends(get_db)):
    row = db.get(LCApplication, app_id)
    if not row:
        raise HTTPException(404)
    if not row.template_id or row.project_cost is None:
        return RedirectResponse(url=f"/applications/{app_id}/classify", status_code=303)

    base, display = display_fees_for_application(row)
    meta = get_template(row.template_id)
    ptype = PROJECT_TYPE_DISPLAY.get(row.category or "", "—")
    ctx = shell_for_application(
        row,
        nav_active="estimations",
        sidebar_active="fee_calculator",
        show_finalize_cta=True,
    )
    ctx.update(
        {
            "app": row,
            "fees": base,
            "display": display,
            "meta": meta,
            "project_type_label": ptype,
            "lc_status_options": LC_STATUS_OPTIONS,
            "lc_status_known": LC_STATUS_KNOWN,
            "fee_display_json": json.dumps(_display_fees_dict(display)),
        }
    )
    return templates.TemplateResponse(request, "assessment.html", ctx)


@app.post("/api/applications/{app_id}/assessment-sync")
def assessment_sync(app_id: int, body: AssessmentSyncIn, db: Session = Depends(get_db)):
    row = db.get(LCApplication, app_id)
    if not row:
        raise HTTPException(404)
    if not row.template_id or row.project_cost is None:
        raise HTTPException(400)
    display = _apply_assessment_inputs(
        row,
        lc_status=body.lc_status,
        date_granted=body.date_granted,
        optional_units=body.optional_units,
        surcharge_amount=body.surcharge_amount,
        waive_zoning_cert=body.waive_zoning_cert,
        lc_fee_amount=body.lc_fee_amount,
        db=db,
    )
    return {"ok": True, "display": _display_fees_dict(display)}


@app.post("/applications/{app_id}/assessment")
def assessment_post(
    app_id: int,
    optional_units: str = Form(""),
    surcharge_amount: str = Form(""),
    waive_zoning_cert: str | None = Form(None),
    lc_status: str = Form(""),
    date_granted: str = Form(""),
    lc_fee_amount: str = Form(""),
    db: Session = Depends(get_db),
):
    row = db.get(LCApplication, app_id)
    if not row:
        raise HTTPException(404)
    if not row.template_id or row.project_cost is None:
        raise HTTPException(400)
    _apply_assessment_inputs(
        row,
        lc_status=lc_status,
        date_granted=date_granted,
        optional_units=optional_units,
        surcharge_amount=surcharge_amount,
        waive_zoning_cert=waive_zoning_cert in ("1", "on", "true", "yes"),
        lc_fee_amount=lc_fee_amount,
        db=db,
    )
    return RedirectResponse(url=f"/applications/{app_id}/assessment", status_code=303)


@app.post("/applications/{app_id}/finalize")
def finalize_post(app_id: int, db: Session = Depends(get_db)):
    row = db.get(LCApplication, app_id)
    if not row or not row.template_id or row.project_cost is None:
        raise HTTPException(404)
    _base, display = display_fees_for_application(row)
    row.lc_fees = display.lc_fee
    row.surcharge = display.surcharge
    row.zc_fees = display.zoning_cert
    row.total = display.total
    db.commit()
    return RedirectResponse(url=f"/applications/{app_id}/assessment", status_code=303)


@app.get("/applications/{app_id}/print", response_class=HTMLResponse)
def print_slip(
    request: Request,
    app_id: int,
    copy: Literal["both", "owner", "file"] = Query(
        "both",
        description="Which slip to print: both sides, owner's copy only, or file copy only.",
    ),
    db: Session = Depends(get_db),
):
    row = db.get(LCApplication, app_id)
    if not row or not row.template_id or row.project_cost is None:
        raise HTTPException(404)
    fee_computed, display = display_fees_for_application(row)
    meta = get_template(row.template_id)
    ptype = PROJECT_TYPE_DISPLAY.get(row.category or "", "—")
    lot_s = f"{row.lot_area_sqm:,.2f}" if row.lot_area_sqm is not None else "—"
    return templates.TemplateResponse(
        request,
        "print_slip.html",
        {
            "app": row,
            "fee_computed": fee_computed,
            "display": display,
            "meta": meta,
            "project_type_label": ptype,
            "lot_display": lot_s,
            "app_date": row.date_of_application.strftime("%b %d, %Y"),
            "print_copy": copy,
        },
    )


@app.get("/applications/{app_id}/pdf")
def download_pdf(app_id: int, db: Session = Depends(get_db)):
    row = db.get(LCApplication, app_id)
    if not row or not row.template_id or row.project_cost is None:
        raise HTTPException(404)
    _base, display = display_fees_for_application(row)
    ptype = PROJECT_TYPE_DISPLAY.get(row.category or "", "—")
    lot_s = f"{row.lot_area_sqm:,.2f}" if row.lot_area_sqm is not None else "—"
    out = EXPORTS_DIR / f"assessment_{row.id}.pdf"
    build_assessment_pdf(
        out_path=out,
        ctrl_no=row.lc_ctrl_no,
        app_date=row.date_of_application.strftime("%b %d, %Y"),
        applicant=row.applicant_name,
        address=row.address,
        project=row.project_name or "",
        location=row.project_location or "",
        lot_area=lot_s,
        project_type_label=ptype,
        project_cost=row.project_cost,
        template_id=row.template_id,
        lc_fee=display.lc_fee,
        surcharge=display.surcharge,
        zoning=display.zoning_cert,
        total=display.total,
        zoning_waived=display.zoning_waived,
    )
    return FileResponse(
        path=out,
        filename=f"LC_{row.lc_ctrl_no.replace('/', '-')}_assessment.pdf",
        media_type="application/pdf",
    )


@app.get("/export/applications.xlsx")
def export_all_xlsx(db: Session = Depends(get_db)):
    rows = db.query(LCApplication).order_by(LCApplication.id.asc()).all()
    out = EXPORTS_DIR / "lc_applications_export.xlsx"
    export_lc_workbook(rows, out)
    return FileResponse(
        path=out,
        filename="lc_applications_export.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
