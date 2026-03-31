from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any, Literal
from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.sessions import SessionMiddleware

from app.auth import (
    LoginRequired,
    hash_password,
    require_admin,
    require_applications_read,
    require_applications_write,
    require_dashboard_read,
    require_export_read,
    require_settings_read,
    require_settings_write,
    require_users_read,
    require_users_write,
    verify_password,
)
from app.config import EXPORTS_DIR, PROJECT_ROOT, SECRET_KEY
from app.doc_requirements import normalize_doc_requirements_post
from app.db import SessionLocal, get_db, init_db
from app.export_excel import export_lc_workbook
from app.geocode import address_suggestions, forward_geocode_address, google_place_coordinates
from app.fees import TEMPLATE_REGISTRY, compute_fees, list_categories, suggest_template
from app.fees.registry import get_template
from app.models import Applicant, LCApplication, RolePermission, User
from app.applicant_service import (
    applicant_suggestion_dicts,
    list_applicants_for_directory,
    resolve_applicant_for_intake,
    search_applicants_for_suggest,
)
from app.permission_defs import MODULES, MODULE_KEYS, ROLE_ADMIN, ROLE_STAFF
from app.pdf_slip import build_assessment_pdf
from app.resolved_fees import DisplayFees, display_fees_for_application
from app.surcharge_items import normalize_surcharge_items_from_api
from app.seeds import run_all_seeds
from app.settings_store import (
    PRINT_PROFILE_LC,
    PRINT_PROFILE_RECEIPT,
    get_print_profile,
    get_zoning_certification_price,
    load_settings,
    save_settings,
)
from app.ui_context import merge_shell, shell_for_application
from app.locational_clearance import router as locational_clearance_router
from app.locational_clearance.router import lc_application_allows_lc_prefill, lc_case_id_for_application

PROJECT_TYPE_DISPLAY = {
    "residential": "RESIDENTIAL",
    "apartment": "APARTMENT/TOWNHOUSE",
    "dormitory": "DORMITORIES",
    "commercial": "COMM'L/INDUS./AGRO-INDUS.",
    "institutional": "INSTITUTIONAL",
    "special_use": "SPECIAL USE",
}

# Non-empty placeholder so the closed <select> shows a label (empty value often renders blank on Windows).
LC_STATUS_UNSET = "__lc_status_unset__"

LC_STATUS_OPTIONS: list[tuple[str, str]] = [
    (LC_STATUS_UNSET, "— Select status —"),
    ("Pending", "Pending"),
    ("Under review", "Under review"),
    ("Approved", "Approved"),
    ("Granted", "Granted"),
    ("Paid", "Paid"),
    ("Denied", "Denied"),
    ("Cancelled", "Cancelled"),
]
LC_STATUS_KNOWN = {v for v, _ in LC_STATUS_OPTIONS if v and v != LC_STATUS_UNSET}


def _normalize_lc_status(raw: str | None) -> str | None:
    s = (raw or "").strip()
    if not s or s == LC_STATUS_UNSET:
        return None
    return s

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))


class SurchargeLineIn(BaseModel):
    name: str = ""
    price: float = 0.0


class AssessmentSyncIn(BaseModel):
    lc_status: str | None = None
    date_granted: str | None = None
    optional_units: str | None = None
    surcharge_items: list[SurchargeLineIn] = Field(default_factory=list)
    waive_zoning_cert: bool = False
    lc_fee_amount: str | None = None


class ApplicantSnapshotIn(BaseModel):
    """Applicant name + application fields shown on the assessment snapshot card."""

    first_name: str = ""
    last_name: str
    middle_name: str | None = None
    suffix: str | None = None
    address: str
    project_cost: float = Field(ge=0)
    category: str
    template_id: str
    lot_area_sqm: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        run_all_seeds(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Zoning Assessment", version="1.0.0", lifespan=lifespan)

app.include_router(locational_clearance_router)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=14 * 24 * 3600,
    same_site="lax",
)


@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired):
    from urllib.parse import quote

    nxt = quote(str(request.url.path), safe="")
    return RedirectResponse(url=f"/login?next={nxt}", status_code=303)


static_dir = PROJECT_ROOT / "app" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request, db: Session = Depends(get_db)):
    uid = request.session.get("user_id")
    if uid is not None:
        u = db.get(User, int(uid))
        if u is not None and u.is_active:
            return RedirectResponse(url="/", status_code=303)
    next_path = (request.query_params.get("next") or "/").strip()
    if not next_path.startswith("/") or next_path.startswith("//"):
        next_path = "/"
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": None, "next": next_path},
    )


@app.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next_url: str = Form("/", alias="next"),
    db: Session = Depends(get_db),
):
    u = db.query(User).filter(User.username == username.strip()).first()
    err: str | None = None
    if not u or not verify_password(password, u.password_hash):
        err = "Invalid username or password."
    elif not u.is_active:
        err = "This account is disabled."
    next_path = (next_url or "/").strip()
    if not next_path.startswith("/") or next_path.startswith("//"):
        next_path = "/"
    if err:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": err, "next": next_path},
        )
    request.session["user_id"] = u.id
    return RedirectResponse(url=next_path, status_code=303)


@app.post("/logout")
def logout_post(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/users", response_class=HTMLResponse)
def users_get(request: Request, db: Session = Depends(get_db), user: User = Depends(require_users_read)):
    rows = db.query(User).order_by(User.created_at.desc()).all()
    open_modal = request.query_params.get("add") == "1"
    return templates.TemplateResponse(
        request,
        "users.html",
        merge_shell(
            {
                "users": rows,
                "user_message": None,
                "user_error": None,
                "add_user_modal_open": open_modal,
                "open_reset_modal_user_id": None,
                "open_edit_modal_user_id": None,
            },
            current_user=user,
            db=db,
            nav_active="users",
            sidebar_active="users",
            project_title="Users",
            project_subtitle="Accounts",
        ),
    )


@app.post("/users")
def users_post(
    request: Request,
    new_username: str = Form(...),
    new_password: str = Form(...),
    full_name: str = Form(""),
    new_role: str = Form(ROLE_STAFF),
    db: Session = Depends(get_db),
    actor: User = Depends(require_users_write),
):
    uname = new_username.strip()
    pwd = new_password
    fn = full_name.strip() or None
    role = (new_role or ROLE_STAFF).strip().lower()
    err: str | None = None
    if len(uname) < 2:
        err = "Username must be at least 2 characters."
    elif len(pwd) < 6:
        err = "Password must be at least 6 characters."
    elif db.query(User).filter(User.username == uname).first():
        err = "That username is already taken."
    elif role not in (ROLE_ADMIN, ROLE_STAFF):
        err = "Invalid role."
    elif actor.role != ROLE_ADMIN and role == ROLE_ADMIN:
        err = "Only administrators can create administrator accounts."
    if err:
        rows = db.query(User).order_by(User.created_at.desc()).all()
        return templates.TemplateResponse(
            request,
            "users.html",
            merge_shell(
                {
                    "users": rows,
                    "user_message": None,
                    "user_error": err,
                    "add_user_modal_open": True,
                    "open_reset_modal_user_id": None,
                    "open_edit_modal_user_id": None,
                },
                current_user=actor,
                db=db,
                nav_active="users",
                sidebar_active="users",
                project_title="Users",
                project_subtitle="Accounts",
            ),
        )
    u = User(
        username=uname,
        password_hash=hash_password(pwd),
        full_name=fn,
        role=role,
        is_active=True,
    )
    db.add(u)
    db.commit()
    rows = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse(
        request,
        "users.html",
        merge_shell(
            {
                "users": rows,
                "user_message": f"User “{uname}” created.",
                "user_error": None,
                "open_reset_modal_user_id": None,
                "open_edit_modal_user_id": None,
            },
            current_user=actor,
            db=db,
            nav_active="users",
            sidebar_active="users",
            project_title="Users",
            project_subtitle="Accounts",
        ),
    )


def _count_admins(db: Session) -> int:
    return db.query(User).filter(User.role == ROLE_ADMIN).count()


@app.post("/users/{user_id}/update")
def users_update(
    request: Request,
    user_id: int,
    edit_username: str = Form(...),
    edit_full_name: str = Form(""),
    edit_role: str = Form(ROLE_STAFF),
    edit_is_active: str | None = Form(None),
    db: Session = Depends(get_db),
    actor: User = Depends(require_users_write),
):
    target = db.get(User, user_id)
    rows = db.query(User).order_by(User.created_at.desc()).all()

    def render(err: str | None, msg: str | None):
        edit_open: int | None = None
        if err and target and (actor.role == ROLE_ADMIN or target.role != ROLE_ADMIN):
            edit_open = target.id
        return templates.TemplateResponse(
            request,
            "users.html",
            merge_shell(
                {
                    "users": rows,
                    "user_message": msg,
                    "user_error": err,
                    "open_reset_modal_user_id": None,
                    "open_edit_modal_user_id": edit_open,
                },
                current_user=actor,
                db=db,
                nav_active="users",
                sidebar_active="users",
                project_title="Users",
                project_subtitle="Accounts",
            ),
        )

    if not target:
        raise HTTPException(404)

    if actor.role != ROLE_ADMIN and target.role == ROLE_ADMIN:
        return render("Only an administrator can change administrator accounts.", None)

    uname = edit_username.strip()
    fn = edit_full_name.strip() or None
    role = (edit_role or ROLE_STAFF).strip().lower()
    is_active = edit_is_active in ("1", "on", "true", "yes")

    err: str | None = None
    if len(uname) < 2:
        err = "Username must be at least 2 characters."
    elif role not in (ROLE_ADMIN, ROLE_STAFF):
        err = "Invalid role."
    elif actor.role != ROLE_ADMIN and role == ROLE_ADMIN:
        err = "Only administrators can assign the administrator role."
    else:
        taken = db.query(User).filter(User.username == uname, User.id != target.id).first()
        if taken:
            err = "That username is already taken."

    if not err and target.id == actor.id and not is_active:
        err = "You cannot deactivate your own account."

    if not err and target.role == ROLE_ADMIN:
        would_remove_admin = role != ROLE_ADMIN or not is_active
        if would_remove_admin and _count_admins(db) == 1:
            err = "Cannot remove or deactivate the last administrator."

    if err:
        return render(err, None)

    target.username = uname
    target.full_name = fn
    target.role = role
    target.is_active = is_active
    db.commit()
    rows = db.query(User).order_by(User.created_at.desc()).all()
    return render(
        None,
        f"User “{uname}” updated.",
    )


@app.post("/users/{user_id}/reset-password")
def users_reset_password(
    request: Request,
    user_id: int,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
    actor: User = Depends(require_users_write),
):
    target = db.get(User, user_id)
    rows = db.query(User).order_by(User.created_at.desc()).all()

    def render(err: str | None, msg: str | None, modal_uid: int | None):
        return templates.TemplateResponse(
            request,
            "users.html",
            merge_shell(
                {
                    "users": rows,
                    "user_message": msg,
                    "user_error": err,
                    "open_reset_modal_user_id": modal_uid,
                    "open_edit_modal_user_id": None,
                },
                current_user=actor,
                db=db,
                nav_active="users",
                sidebar_active="users",
                project_title="Users",
                project_subtitle="Accounts",
            ),
        )

    if not target:
        raise HTTPException(404)

    if actor.role != ROLE_ADMIN and target.role == ROLE_ADMIN:
        return render("Only an administrator can reset an administrator’s password.", None, None)

    pwd_new = (new_password or "").strip()
    pwd_confirm = (confirm_password or "").strip()

    err: str | None = None
    if not pwd_new or not pwd_confirm:
        err = "Enter and confirm the new password."
    elif pwd_new != pwd_confirm:
        err = "New password and confirmation do not match."
    elif len(pwd_new) < 6:
        err = "New password must be at least 6 characters."

    if err:
        return render(err, None, target.id)

    target.password_hash = hash_password(pwd_new)
    db.commit()
    rows = db.query(User).order_by(User.created_at.desc()).all()
    uname = target.username
    return render(None, f"Password updated for “{uname}”.", None)


@app.get("/permissions", response_class=HTMLResponse)
def permissions_get(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = {r.module_key: r for r in db.query(RolePermission).filter(RolePermission.role == ROLE_STAFF).all()}
    return templates.TemplateResponse(
        request,
        "permissions.html",
        merge_shell(
            {
                "modules": MODULES,
                "staff_perms": rows,
                "saved": False,
            },
            current_user=admin,
            db=db,
            nav_active="permissions",
            sidebar_active="permissions",
            project_title="Role permissions",
            project_subtitle="Staff access",
        ),
    )


@app.post("/permissions")
async def permissions_post(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    form = await request.form()
    for key in MODULE_KEYS:
        read = form.get(f"read_{key}") in ("1", "on", "true", "yes")
        write = form.get(f"write_{key}") in ("1", "on", "true", "yes")
        if write:
            read = True
        row = (
            db.query(RolePermission)
            .filter(RolePermission.role == ROLE_STAFF, RolePermission.module_key == key)
            .first()
        )
        if row:
            row.can_read = read
            row.can_write = write
        else:
            db.add(RolePermission(role=ROLE_STAFF, module_key=key, can_read=read, can_write=write))
    db.commit()
    rows = {r.module_key: r for r in db.query(RolePermission).filter(RolePermission.role == ROLE_STAFF).all()}
    return templates.TemplateResponse(
        request,
        "permissions.html",
        merge_shell(
            {
                "modules": MODULES,
                "staff_perms": rows,
                "saved": True,
            },
            current_user=admin,
            db=db,
            nav_active="permissions",
            sidebar_active="permissions",
            project_title="Role permissions",
            project_subtitle="Staff access",
        ),
    )


def _parse_date(s: str | None) -> date | None:
    if not s or not str(s).strip():
        return None
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def _parse_optional_float(s: str | None) -> float | None:
    t = (s or "").strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _sanitize_lat_lon(lat: float | None, lon: float | None) -> tuple[float | None, float | None]:
    if lat is None or lon is None:
        return None, None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None, None
    return lat, lon


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
        "surcharge_itemized": d.surcharge_itemized,
        "surcharge_lines": [{"name": x["name"], "price": x["price"]} for x in d.surcharge_lines],
        "surcharge_items": [{"name": x["name"], "price": x["price"]} for x in d.surcharge_items],
    }


def _apply_assessment_inputs(
    row: LCApplication,
    *,
    lc_status: str | None,
    date_granted: str | None,
    optional_units: str | None,
    surcharge_items: list[SurchargeLineIn] | None,
    waive_zoning_cert: bool,
    lc_fee_amount: str | None,
    db: Session,
) -> DisplayFees:
    row.lc_status = _normalize_lc_status(lc_status)
    row.date_granted = _parse_date(date_granted)
    ou = (optional_units or "").strip()
    row.optional_units = float(ou) if ou else None
    base = compute_fees(
        row.template_id or "",
        float(row.project_cost or 0),
        lot_area_sqm=row.lot_area_sqm,
        optional_units=row.optional_units,
    )
    if surcharge_items is not None:
        row.surcharge_items = normalize_surcharge_items_from_api([s.model_dump() for s in surcharge_items])
        row.surcharge_override = None
    row.lc_fee_override = _parse_lc_fee_override(lc_fee_amount, base.lc_fee)
    row.waive_zoning_cert = waive_zoning_cert
    db.commit()
    db.refresh(row)
    _base, display = display_fees_for_application(row)
    return display


@app.get("/api/suggest-template")
def api_suggest_template(
    category: str,
    project_cost: float,
    _user: User = Depends(require_applications_read),
):
    return {"template_id": suggest_template(category, project_cost)}


@app.get("/api/address-suggest")
def api_address_suggest(
    q: str = Query("", max_length=500),
    _user: User = Depends(require_applications_read),
):
    """Autocomplete for applicant address (Nominatim by default, or Google Places if key is set)."""
    suggestions, provider = address_suggestions(q, limit=8)
    return {"suggestions": suggestions, "provider": provider}


@app.get("/api/google-place-details")
def api_google_place_details(
    place_id: str = Query("", max_length=512),
    _user: User = Depends(require_applications_read),
):
    """Lat/lon for a Google Places prediction (after user selects a suggestion)."""
    t = google_place_coordinates(place_id.strip())
    if t is None:
        return {"lat": None, "lon": None}
    lat, lon = t
    return {"lat": lat, "lon": lon}


@app.get("/api/geocode-forward")
def api_geocode_forward(
    q: str = Query("", max_length=512),
    _user: User = Depends(require_applications_read),
):
    """Approximate coordinates for a full address (Nominatim first hit). Map preview when no pin saved."""
    t = forward_geocode_address(q)
    if t is None:
        return {"lat": None, "lon": None}
    lat, lon = t
    return {"lat": lat, "lon": lon}


@app.get("/settings", response_class=HTMLResponse)
def settings_get(request: Request, db: Session = Depends(get_db), user: User = Depends(require_settings_read)):
    s = load_settings()
    pp = s["print_profiles"]
    return templates.TemplateResponse(
        request,
        "settings.html",
        merge_shell(
            {
                "zoning_certification_price": s["zoning_certification_price"],
                "print_lc": pp[PRINT_PROFILE_LC],
                "print_rcpt": pp[PRINT_PROFILE_RECEIPT],
                "saved": False,
            },
            current_user=user,
            db=db,
            nav_active="settings",
            sidebar_active="settings",
            project_title="Settings",
            project_subtitle="Fee defaults",
        ),
    )


@app.post("/settings")
def settings_post(
    request: Request,
    zoning_certification_price: str = Form(...),
    lc_republic_label: str = Form(""),
    lc_municipality_label: str = Form(""),
    lc_office_label: str = Form(""),
    lc_logo_static_relpath: str = Form(""),
    lc_signatory_name: str = Form(""),
    lc_signatory_role: str = Form(""),
    rcpt_republic_label: str = Form(""),
    rcpt_municipality_label: str = Form(""),
    rcpt_office_label: str = Form(""),
    rcpt_logo_static_relpath: str = Form(""),
    rcpt_signatory_name: str = Form(""),
    rcpt_signatory_role: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_settings_write),
):
    try:
        v = float(zoning_certification_price)
    except ValueError:
        v = get_zoning_certification_price()
    save_settings(
        {
            "zoning_certification_price": max(0.0, v),
            "print_profiles": {
                PRINT_PROFILE_LC: {
                    "republic_label": lc_republic_label,
                    "municipality_label": lc_municipality_label,
                    "office_label": lc_office_label,
                    "logo_static_relpath": lc_logo_static_relpath,
                    "signatory_name": lc_signatory_name,
                    "signatory_role": lc_signatory_role,
                },
                PRINT_PROFILE_RECEIPT: {
                    "republic_label": rcpt_republic_label,
                    "municipality_label": rcpt_municipality_label,
                    "office_label": rcpt_office_label,
                    "logo_static_relpath": rcpt_logo_static_relpath,
                    "signatory_name": rcpt_signatory_name,
                    "signatory_role": rcpt_signatory_role,
                },
            },
        }
    )
    s = load_settings()
    pp = s["print_profiles"]
    return templates.TemplateResponse(
        request,
        "settings.html",
        merge_shell(
            {
                "zoning_certification_price": s["zoning_certification_price"],
                "print_lc": pp[PRINT_PROFILE_LC],
                "print_rcpt": pp[PRINT_PROFILE_RECEIPT],
                "saved": True,
            },
            current_user=user,
            db=db,
            nav_active="settings",
            sidebar_active="settings",
            project_title="Settings",
            project_subtitle="Fee defaults",
        ),
    )


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_dashboard_read)):
    apps = (
        db.scalars(
            select(LCApplication)
            .options(joinedload(LCApplication.applicant))
            .order_by(LCApplication.created_at.desc())
            .limit(100)
        )
        .unique()
        .all()
    )
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
            current_user=user,
            db=db,
            nav_active="dashboard",
            sidebar_active="overview",
        ),
    )


@app.get("/applications/new", response_class=HTMLResponse)
def new_application_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_applications_write),
    reuse: int | None = Query(None, description="Existing applicant id to pre-fill the form."),
):
    today = date.today().isoformat()
    reuse_applicant = db.get(Applicant, reuse) if reuse is not None else None
    return templates.TemplateResponse(
        request,
        "new.html",
        merge_shell(
            {
                "today": today,
                "lc_status_options": LC_STATUS_OPTIONS,
                "reuse_applicant": reuse_applicant,
            },
            current_user=user,
            db=db,
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
    applicant_first_name: str = Form(...),
    applicant_last_name: str = Form(...),
    applicant_middle_name: str = Form(""),
    applicant_suffix: str = Form(""),
    existing_applicant_id: str = Form(""),
    address: str = Form(...),
    address_lat: str = Form(""),
    address_lon: str = Form(""),
    project_name: str = Form(""),
    project_location: str = Form(""),
    doc_requirements: str = Form(""),
    lc_status: str = Form(""),
    date_granted: str = Form(""),
    db: Session = Depends(get_db),
    _user: User = Depends(require_applications_write),
):
    try:
        ap = resolve_applicant_for_intake(
            db,
            existing_applicant_id=existing_applicant_id,
            first_name=applicant_first_name,
            last_name=applicant_last_name,
            middle_name=applicant_middle_name,
            suffix=applicant_suffix,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    la, lo = _sanitize_lat_lon(_parse_optional_float(address_lat), _parse_optional_float(address_lon))
    row = LCApplication(
        lc_ctrl_no=lc_ctrl_no.strip(),
        date_of_application=_parse_date(date_of_application) or date.today(),
        applicant_id=ap.id,
        address=address.strip(),
        address_lat=la,
        address_lon=lo,
        project_name=project_name.strip() or None,
        project_location=project_location.strip() or None,
        doc_requirements=normalize_doc_requirements_post(doc_requirements),
        lc_status=_normalize_lc_status(lc_status),
        date_granted=_parse_date(date_granted),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return RedirectResponse(url=f"/applications/{row.id}/classify", status_code=303)


@app.get("/api/applicants/suggest")
def applicants_suggest(
    q: str = "",
    db: Session = Depends(get_db),
    _user: User = Depends(require_applications_read),
):
    found = search_applicants_for_suggest(db, q, limit=15)
    return applicant_suggestion_dicts(db, found)


@app.get("/applicants", response_class=HTMLResponse)
def applicants_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_applications_read),
    q: str | None = Query(None, description="Filter by name (optional)."),
):
    found = list_applicants_for_directory(db, q, limit=500)
    rows = applicant_suggestion_dicts(db, found)
    return templates.TemplateResponse(
        request,
        "applicants_list.html",
        merge_shell(
            {
                "applicant_rows": rows,
                "search_q": (q or "").strip(),
            },
            current_user=user,
            db=db,
            nav_active="dashboard",
            sidebar_active="applicants",
            project_title="Applicants",
            project_subtitle="Directory",
        ),
    )


@app.get("/applicants/{applicant_id}", response_class=HTMLResponse)
def applicant_detail(
    request: Request,
    applicant_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_applications_read),
):
    ap = db.get(Applicant, applicant_id)
    if not ap:
        raise HTTPException(status_code=404)
    apps = (
        db.scalars(
            select(LCApplication)
            .where(LCApplication.applicant_id == applicant_id)
            .order_by(LCApplication.created_at.desc())
        )
        .all()
    )
    return templates.TemplateResponse(
        request,
        "applicant_detail.html",
        merge_shell(
            {
                "applicant": ap,
                "applications": apps,
            },
            current_user=user,
            db=db,
            nav_active="dashboard",
            sidebar_active="applicants",
            project_title=ap.display_name,
            project_subtitle="Applicant history",
        ),
    )


@app.get("/applications/{app_id}/classify", response_class=HTMLResponse)
def classify_get(
    request: Request,
    app_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_applications_read),
):
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
    ctx = shell_for_application(
        row,
        nav_active="estimations",
        sidebar_active="site_analysis",
        current_user=user,
        db=db,
    )
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
    _user: User = Depends(require_applications_write),
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


@app.patch("/api/applications/{app_id}/applicant-snapshot")
def applicant_snapshot_patch(
    app_id: int,
    body: ApplicantSnapshotIn,
    db: Session = Depends(get_db),
    _user: User = Depends(require_applications_write),
):
    row = db.scalars(
        select(LCApplication)
        .where(LCApplication.id == app_id)
        .options(joinedload(LCApplication.applicant))
    ).first()
    if not row:
        raise HTTPException(404)
    if not row.template_id or row.project_cost is None:
        raise HTTPException(400, "Application must be classified first.")
    ap = row.applicant
    if not ap:
        raise HTTPException(400, "Application has no applicant record.")

    last = body.last_name.strip()
    if not last:
        raise HTTPException(status_code=422, detail="Last name is required.")

    try:
        tmeta = get_template(body.template_id.strip())
    except KeyError:
        raise HTTPException(400, "Invalid assessment template.") from None
    cat = body.category.strip()
    if tmeta.category != cat:
        raise HTTPException(400, "Category does not match the selected template.")

    ap.first_name = (body.first_name or "").strip()
    ap.last_name = last
    ap.middle_name = (body.middle_name or "").strip() or None
    ap.suffix = (body.suffix or "").strip() or None

    row.address = (body.address or "").strip()
    row.project_cost = float(body.project_cost)
    row.category = cat
    row.template_id = body.template_id.strip()
    la = (body.lot_area_sqm or "").strip()
    row.lot_area_sqm = float(la) if la else None

    db.commit()
    return {"ok": True}


@app.get("/applications/{app_id}/assessment", response_class=HTMLResponse)
def assessment_get(
    request: Request,
    app_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_applications_read),
):
    row = db.scalars(
        select(LCApplication)
        .where(LCApplication.id == app_id)
        .options(joinedload(LCApplication.applicant))
    ).first()
    if not row:
        raise HTTPException(404)
    if not row.template_id or row.project_cost is None:
        return RedirectResponse(url=f"/applications/{app_id}/classify", status_code=303)

    base, display = display_fees_for_application(row)
    meta = get_template(row.template_id)
    ptype = PROJECT_TYPE_DISPLAY.get(row.category or "", "—")
    cat_labels = dict(list_categories())
    grouped: dict[str, list[Any]] = {}
    for t in TEMPLATE_REGISTRY:
        grouped.setdefault(t.category, []).append(t)
    suggested = None
    if row.category and row.project_cost is not None:
        suggested = suggest_template(row.category, row.project_cost)
    ctx = shell_for_application(
        row,
        nav_active="estimations",
        sidebar_active="fee_calculator",
        current_user=user,
        db=db,
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
            "lc_forms_from_application_enabled": lc_application_allows_lc_prefill(row.lc_status),
            "lc_case_for_application_id": lc_case_id_for_application(db, app_id),
            "categories": list_categories(),
            "templates_grouped": grouped,
            "cat_labels": cat_labels,
            "snapshot_suggested_template": suggested,
        }
    )
    return templates.TemplateResponse(request, "assessment.html", ctx)


@app.post("/api/applications/{app_id}/assessment-sync")
def assessment_sync(
    app_id: int,
    body: AssessmentSyncIn,
    db: Session = Depends(get_db),
    _user: User = Depends(require_applications_write),
):
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
        surcharge_items=body.surcharge_items,
        waive_zoning_cert=body.waive_zoning_cert,
        lc_fee_amount=body.lc_fee_amount,
        db=db,
    )
    return {"ok": True, "display": _display_fees_dict(display)}


@app.post("/applications/{app_id}/assessment")
def assessment_post(
    app_id: int,
    optional_units: str = Form(""),
    surcharge_items_json: str = Form(""),
    waive_zoning_cert: str | None = Form(None),
    lc_status: str = Form(""),
    date_granted: str = Form(""),
    lc_fee_amount: str = Form(""),
    db: Session = Depends(get_db),
    _user: User = Depends(require_applications_write),
):
    row = db.get(LCApplication, app_id)
    if not row:
        raise HTTPException(404)
    if not row.template_id or row.project_cost is None:
        raise HTTPException(400)
    sur_items: list[SurchargeLineIn] = []
    raw = (surcharge_items_json or "").strip()
    if raw:
        try:
            arr = json.loads(raw)
            if isinstance(arr, list):
                sur_items = []
                for x in arr:
                    if not isinstance(x, dict):
                        continue
                    sur_items.append(
                        SurchargeLineIn(name=str(x.get("name") or ""), price=float(x.get("price") or 0))
                    )
            else:
                sur_items = []
        except (json.JSONDecodeError, TypeError, ValueError):
            sur_items = []
    else:
        sur_items = []
    _apply_assessment_inputs(
        row,
        lc_status=lc_status,
        date_granted=date_granted,
        optional_units=optional_units,
        surcharge_items=sur_items,
        waive_zoning_cert=waive_zoning_cert in ("1", "on", "true", "yes"),
        lc_fee_amount=lc_fee_amount,
        db=db,
    )
    return RedirectResponse(url=f"/applications/{app_id}/assessment", status_code=303)


@app.post("/applications/{app_id}/finalize")
def finalize_post(app_id: int, db: Session = Depends(get_db), _user: User = Depends(require_applications_write)):
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
    _user: User = Depends(require_applications_read),
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
            "app_date": row.date_of_application.strftime("%m/%d/%Y"),
            "print_copy": copy,
            "print_branding": get_print_profile(PRINT_PROFILE_LC),
        },
    )


@app.get("/applications/{app_id}/pdf")
def download_pdf(
    app_id: int,
    inline: bool = Query(False, description="If true, serve PDF for inline viewing (e.g. modal iframe)."),
    copy: Literal["owner", "file"] = Query(
        "owner",
        description="Which copy label to print on the slip (owner's copy vs file copy).",
    ),
    db: Session = Depends(get_db),
    _user: User = Depends(require_applications_read),
):
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
        app_date=row.date_of_application.strftime("%m/%d/%Y"),
        applicant=row.applicant_display_name,
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
        surcharge_lines=list(display.surcharge_lines),
        surcharge_itemized=display.surcharge_itemized,
        zoning_waived=display.zoning_waived,
        branding=get_print_profile(PRINT_PROFILE_LC),
        copy_kind=copy,
    )
    safe_name = f"LC_{row.lc_ctrl_no.replace('/', '-')}_assessment.pdf"
    if inline:
        return FileResponse(
            path=out,
            filename=safe_name,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
        )
    return FileResponse(path=out, filename=safe_name, media_type="application/pdf")


@app.get("/export/applications.xlsx")
def export_all_xlsx(db: Session = Depends(get_db), _user: User = Depends(require_export_read)):
    rows = (
        db.scalars(
            select(LCApplication)
            .options(joinedload(LCApplication.applicant))
            .order_by(LCApplication.id.asc())
        )
        .unique()
        .all()
    )
    out = EXPORTS_DIR / "lc_applications_export.xlsx"
    export_lc_workbook(rows, out)
    return FileResponse(
        path=out,
        filename="lc_applications_export.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
