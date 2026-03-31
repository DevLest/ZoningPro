from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.applicant_service import resolve_applicant_for_intake
from app.auth import (
    require_locational_clearance_read,
    require_locational_clearance_write,
)
from app.config import PROJECT_ROOT
from app.db import get_db
from app.models import Applicant, LCApplication, LocationalClearanceCase, User
from app.settings_store import PRINT_PROFILE_LC, get_print_profile
from app.ui_context import merge_shell

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))

router = APIRouter(prefix="/locational-clearance", tags=["locational_clearance"])


def lc_application_allows_lc_prefill(lc_status: str | None) -> bool:
    """Locational clearance prefill from a fee application is allowed once LC status is Paid."""
    return (lc_status or "").strip().casefold() == "paid"


def lc_case_locked_to_paid_fee_application(db: Session, lc_application_id: int | None) -> bool:
    if lc_application_id is None:
        return False
    la = db.get(LCApplication, lc_application_id)
    return la is not None and lc_application_allows_lc_prefill(la.lc_status)


def _locked_form_strings_from_fee_la(la: LCApplication) -> dict[str, str]:
    """Canonical string values from the fee application; used when the LC case is locked to a paid fee app."""
    ap = la.applicant
    if ap is None:
        raise ValueError("Fee application has no applicant record.")
    return {
        "application_number": la.lc_ctrl_no,
        "date_of_receipt": la.date_of_application.isoformat() if la.date_of_application else "",
        "or_date": la.date_granted.isoformat() if la.date_granted else "",
        "amount_paid": str(la.total) if la.total is not None else "",
        "applicant_address": la.address,
        "corporation_address": la.address,
        "project_title": (la.project_name or "").strip(),
        "project_location": (la.project_location or "").strip(),
        "lot_area_sqm": str(la.lot_area_sqm) if la.lot_area_sqm is not None else "",
        "project_cost_amount": str(la.project_cost) if la.project_cost is not None else "",
        "applicant_first_name": ap.first_name or "",
        "applicant_last_name": ap.last_name or "",
        "applicant_middle_name": ap.middle_name or "",
        "applicant_suffix": ap.suffix or "",
    }


def _parse_date(s: str | None) -> date | None:
    if not s or not str(s).strip():
        return None
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def _parse_float(s: str | None) -> float | None:
    t = (s or "").strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _bool_from_form(v: str | None) -> bool | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    return v in ("1", "on", "true", "yes")


def _apply_form_to_case(
    row: LocationalClearanceCase,
    *,
    application_number: str,
    date_of_receipt: str,
    or_number: str,
    or_date: str,
    amount_paid: str,
    corporation_name: str,
    applicant_address: str,
    corporation_address: str,
    authorized_representative_name: str,
    authorized_representative_address: str,
    project_title: str,
    project_location: str,
    lot_area_sqm: str,
    building_area_sqm: str,
    project_nature: str,
    project_nature_other: str,
    right_over_land: str,
    right_over_land_other: str,
    land_use_duration: str,
    existing_land_use: str,
    project_cost_words: str,
    project_cost_amount: str,
    lc_notice_required: str | None,
    lc_notice_dates_filed: str,
    lc_notice_actions: str,
    release_mode: str,
    release_mail_to: str,
    decision_number: str,
    decision_date: str,
    decision_outcome: str,
    decision_headline: str,
    tct_oct_number: str,
    zoning_classification: str,
    cert_parcel_location: str,
    cert_area_words: str,
    cert_registered_owner: str,
    cert_lot_numbers: str,
    cert_issued_to: str,
    cert_purpose: str,
    cert_date: str,
    cert_place: str,
    additional_conditions: str,
) -> None:
    row.application_number = application_number.strip()
    row.date_of_receipt = _parse_date(date_of_receipt)
    row.or_number = or_number.strip() or None
    row.or_date = _parse_date(or_date)
    row.amount_paid = _parse_float(amount_paid)
    row.corporation_name = corporation_name.strip() or None
    row.applicant_address = applicant_address.strip()
    row.corporation_address = corporation_address.strip() or None
    row.authorized_representative_name = authorized_representative_name.strip() or None
    row.authorized_representative_address = authorized_representative_address.strip() or None
    row.project_title = project_title.strip()
    row.project_location = project_location.strip() or None
    row.lot_area_sqm = _parse_float(lot_area_sqm)
    row.building_area_sqm = _parse_float(building_area_sqm)
    row.project_nature = project_nature.strip() or None
    row.project_nature_other = project_nature_other.strip() or None
    row.right_over_land = right_over_land.strip() or None
    row.right_over_land_other = right_over_land_other.strip() or None
    row.land_use_duration = land_use_duration.strip() or None
    row.existing_land_use = existing_land_use.strip() or None
    row.project_cost_words = project_cost_words.strip() or None
    row.project_cost_amount = _parse_float(project_cost_amount)
    row.lc_notice_required = _bool_from_form(lc_notice_required)
    row.lc_notice_dates_filed = lc_notice_dates_filed.strip() or None
    row.lc_notice_actions = lc_notice_actions.strip() or None
    row.release_mode = release_mode.strip() or None
    row.release_mail_to = release_mail_to.strip() or None
    row.decision_number = decision_number.strip() or None
    row.decision_date = _parse_date(decision_date)
    row.decision_outcome = decision_outcome.strip() or None
    row.decision_headline = decision_headline.strip() or None
    row.tct_oct_number = tct_oct_number.strip() or None
    row.zoning_classification = zoning_classification.strip() or None
    row.cert_parcel_location = cert_parcel_location.strip() or None
    row.cert_area_words = cert_area_words.strip() or None
    row.cert_registered_owner = cert_registered_owner.strip() or None
    row.cert_lot_numbers = cert_lot_numbers.strip() or None
    row.cert_issued_to = cert_issued_to.strip() or None
    row.cert_purpose = cert_purpose.strip() or None
    row.cert_date = _parse_date(cert_date)
    row.cert_place = cert_place.strip() or None
    row.additional_conditions = additional_conditions.strip() or None


@router.get("/", response_class=HTMLResponse)
def lc_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_locational_clearance_read),
):
    rows = (
        db.scalars(
            select(LocationalClearanceCase)
            .options(joinedload(LocationalClearanceCase.applicant))
            .order_by(LocationalClearanceCase.created_at.desc())
            .limit(200)
        )
        .unique()
        .all()
    )
    return templates.TemplateResponse(
        request,
        "locational_clearance/list.html",
        merge_shell(
            {"cases": rows},
            current_user=user,
            db=db,
            nav_active="dashboard",
            sidebar_active="lc_cases",
            project_title="Locational clearance",
            project_subtitle="LC forms",
        ),
    )


def _prefill_from_lc_application(db: Session, lc_id: int) -> dict:
    la = db.get(LCApplication, lc_id)
    if not la:
        return {}
    ap = la.applicant
    return {
        "reuse_applicant": ap,
        "prefill_lc_application_id": la.id,
        "applicant_address": la.address,
        "corporation_address": la.address,
        "project_title": (la.project_name or "").strip(),
        "project_location": (la.project_location or "").strip(),
        "lot_area_sqm": la.lot_area_sqm,
        "project_cost_amount": la.project_cost,
        "amount_paid": la.total,
        "application_number": la.lc_ctrl_no,
        "date_of_receipt": la.date_of_application.isoformat() if la.date_of_application else "",
        "or_date": la.date_granted.isoformat() if la.date_granted else "",
    }


@router.get("/new", response_class=HTMLResponse)
def lc_new_get(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_locational_clearance_write),
    applicant: int | None = Query(None),
    lc_application: int | None = Query(None, alias="lc_application"),
):
    today = date.today().isoformat()
    reuse_applicant = db.get(Applicant, applicant) if applicant is not None else None
    prefill: dict = {}
    prefill_lc_application_id: int | None = None
    if lc_application is not None:
        la = db.get(LCApplication, lc_application)
        if not la:
            raise HTTPException(status_code=404)
        if not lc_application_allows_lc_prefill(la.lc_status):
            return RedirectResponse(
                url=f"/applications/{lc_application}/assessment?lc_forms=locked",
                status_code=303,
            )
        prefill = _prefill_from_lc_application(db, lc_application)
        if prefill.get("reuse_applicant"):
            reuse_applicant = prefill["reuse_applicant"]
        prefill_lc_application_id = prefill.get("prefill_lc_application_id")
    prefill_existing_applicant_id = str(reuse_applicant.id) if reuse_applicant else ""
    return templates.TemplateResponse(
        request,
        "locational_clearance/form.html",
        merge_shell(
            {
                "case_row": None,
                "is_edit": False,
                "today": today,
                "reuse_applicant": reuse_applicant,
                "prefill": prefill,
                "prefill_lc_application_id": prefill_lc_application_id,
                "prefill_existing_applicant_id": prefill_existing_applicant_id,
                "lc_fee_app_fields_locked": prefill_lc_application_id is not None,
            },
            current_user=user,
            db=db,
            nav_active="new_lc_case",
            sidebar_active="lc_new",
            project_title="New LC case",
            project_subtitle="Forms 1, 2 & certification",
        ),
    )


@router.post("/new")
def lc_new_post(
    db: Session = Depends(get_db),
    _user: User = Depends(require_locational_clearance_write),
    existing_applicant_id: str = Form(""),
    applicant_first_name: str = Form(...),
    applicant_last_name: str = Form(...),
    applicant_middle_name: str = Form(""),
    applicant_suffix: str = Form(""),
    lc_application_id: str = Form(""),
    application_number: str = Form(""),
    date_of_receipt: str = Form(""),
    or_number: str = Form(""),
    or_date: str = Form(""),
    amount_paid: str = Form(""),
    corporation_name: str = Form(""),
    applicant_address: str = Form(...),
    corporation_address: str = Form(""),
    authorized_representative_name: str = Form(""),
    authorized_representative_address: str = Form(""),
    project_title: str = Form(...),
    project_location: str = Form(""),
    lot_area_sqm: str = Form(""),
    building_area_sqm: str = Form(""),
    project_nature: str = Form(""),
    project_nature_other: str = Form(""),
    right_over_land: str = Form(""),
    right_over_land_other: str = Form(""),
    land_use_duration: str = Form(""),
    existing_land_use: str = Form(""),
    project_cost_words: str = Form(""),
    project_cost_amount: str = Form(""),
    lc_notice_required: str | None = Form(None),
    lc_notice_dates_filed: str = Form(""),
    lc_notice_actions: str = Form(""),
    release_mode: str = Form(""),
    release_mail_to: str = Form(""),
    decision_number: str = Form(""),
    decision_date: str = Form(""),
    decision_outcome: str = Form(""),
    decision_headline: str = Form(""),
    tct_oct_number: str = Form(""),
    zoning_classification: str = Form(""),
    cert_parcel_location: str = Form(""),
    cert_area_words: str = Form(""),
    cert_registered_owner: str = Form(""),
    cert_lot_numbers: str = Form(""),
    cert_issued_to: str = Form(""),
    cert_purpose: str = Form(""),
    cert_date: str = Form(""),
    cert_place: str = Form(""),
    additional_conditions: str = Form(""),
):
    la_id: int | None = None
    la_row: LCApplication | None = None
    t = (lc_application_id or "").strip()
    if t.isdigit():
        la_id = int(t)
        la_row = (
            db.scalars(
                select(LCApplication)
                .where(LCApplication.id == la_id)
                .options(joinedload(LCApplication.applicant))
            )
            .unique()
            .first()
        )
        if la_row is None:
            la_id = None
        elif not lc_application_allows_lc_prefill(la_row.lc_status):
            raise HTTPException(
                status_code=400,
                detail="Fee application must have LC status Paid before linking to an LC case.",
            )
    locked = la_id is not None and la_row is not None
    if locked:
        try:
            fix = _locked_form_strings_from_fee_la(la_row)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        application_number = fix["application_number"]
        date_of_receipt = fix["date_of_receipt"]
        or_date = fix["or_date"]
        amount_paid = fix["amount_paid"]
        applicant_address = fix["applicant_address"]
        corporation_address = fix["corporation_address"]
        project_title = fix["project_title"]
        project_location = fix["project_location"]
        lot_area_sqm = fix["lot_area_sqm"]
        project_cost_amount = fix["project_cost_amount"]
        applicant_first_name = fix["applicant_first_name"]
        applicant_last_name = fix["applicant_last_name"]
        applicant_middle_name = fix["applicant_middle_name"]
        applicant_suffix = fix["applicant_suffix"]
        ap = la_row.applicant
        if ap is None:
            raise HTTPException(status_code=400, detail="Fee application has no applicant record.")
    else:
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
    row = LocationalClearanceCase(applicant_id=ap.id, lc_application_id=la_id)
    _apply_form_to_case(
        row,
        application_number=application_number,
        date_of_receipt=date_of_receipt,
        or_number=or_number,
        or_date=or_date,
        amount_paid=amount_paid,
        corporation_name=corporation_name,
        applicant_address=applicant_address,
        corporation_address=corporation_address,
        authorized_representative_name=authorized_representative_name,
        authorized_representative_address=authorized_representative_address,
        project_title=project_title,
        project_location=project_location,
        lot_area_sqm=lot_area_sqm,
        building_area_sqm=building_area_sqm,
        project_nature=project_nature,
        project_nature_other=project_nature_other,
        right_over_land=right_over_land,
        right_over_land_other=right_over_land_other,
        land_use_duration=land_use_duration,
        existing_land_use=existing_land_use,
        project_cost_words=project_cost_words,
        project_cost_amount=project_cost_amount,
        lc_notice_required=lc_notice_required,
        lc_notice_dates_filed=lc_notice_dates_filed,
        lc_notice_actions=lc_notice_actions,
        release_mode=release_mode,
        release_mail_to=release_mail_to,
        decision_number=decision_number,
        decision_date=decision_date,
        decision_outcome=decision_outcome,
        decision_headline=decision_headline,
        tct_oct_number=tct_oct_number,
        zoning_classification=zoning_classification,
        cert_parcel_location=cert_parcel_location,
        cert_area_words=cert_area_words,
        cert_registered_owner=cert_registered_owner,
        cert_lot_numbers=cert_lot_numbers,
        cert_issued_to=cert_issued_to,
        cert_purpose=cert_purpose,
        cert_date=cert_date,
        cert_place=cert_place,
        additional_conditions=additional_conditions,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return RedirectResponse(url=f"/locational-clearance/{row.id}", status_code=303)


@router.get("/{case_id}", response_class=HTMLResponse)
def lc_detail_get(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_locational_clearance_read),
):
    row = (
        db.scalars(
            select(LocationalClearanceCase)
            .where(LocationalClearanceCase.id == case_id)
            .options(
                joinedload(LocationalClearanceCase.applicant),
                joinedload(LocationalClearanceCase.lc_application),
            )
        )
        .unique()
        .first()
    )
    if not row:
        raise HTTPException(status_code=404)
    fee_locked = lc_case_locked_to_paid_fee_application(db, row.lc_application_id)
    return templates.TemplateResponse(
        request,
        "locational_clearance/form.html",
        merge_shell(
            {
                "case_row": row,
                "is_edit": True,
                "today": date.today().isoformat(),
                "reuse_applicant": row.applicant,
                "prefill": {},
                "prefill_lc_application_id": row.lc_application_id,
                "prefill_existing_applicant_id": str(row.applicant_id),
                "lc_fee_app_fields_locked": fee_locked,
            },
            current_user=user,
            db=db,
            nav_active="dashboard",
            sidebar_active="lc_cases",
            project_title=row.application_number or f"Case #{row.id}",
            project_subtitle="Locational clearance",
        ),
    )


@router.post("/{case_id}")
def lc_detail_post(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_locational_clearance_write),
    existing_applicant_id: str = Form(""),
    applicant_first_name: str = Form(...),
    applicant_last_name: str = Form(...),
    applicant_middle_name: str = Form(""),
    applicant_suffix: str = Form(""),
    lc_application_id: str = Form(""),
    application_number: str = Form(""),
    date_of_receipt: str = Form(""),
    or_number: str = Form(""),
    or_date: str = Form(""),
    amount_paid: str = Form(""),
    corporation_name: str = Form(""),
    applicant_address: str = Form(...),
    corporation_address: str = Form(""),
    authorized_representative_name: str = Form(""),
    authorized_representative_address: str = Form(""),
    project_title: str = Form(...),
    project_location: str = Form(""),
    lot_area_sqm: str = Form(""),
    building_area_sqm: str = Form(""),
    project_nature: str = Form(""),
    project_nature_other: str = Form(""),
    right_over_land: str = Form(""),
    right_over_land_other: str = Form(""),
    land_use_duration: str = Form(""),
    existing_land_use: str = Form(""),
    project_cost_words: str = Form(""),
    project_cost_amount: str = Form(""),
    lc_notice_required: str | None = Form(None),
    lc_notice_dates_filed: str = Form(""),
    lc_notice_actions: str = Form(""),
    release_mode: str = Form(""),
    release_mail_to: str = Form(""),
    decision_number: str = Form(""),
    decision_date: str = Form(""),
    decision_outcome: str = Form(""),
    decision_headline: str = Form(""),
    tct_oct_number: str = Form(""),
    zoning_classification: str = Form(""),
    cert_parcel_location: str = Form(""),
    cert_area_words: str = Form(""),
    cert_registered_owner: str = Form(""),
    cert_lot_numbers: str = Form(""),
    cert_issued_to: str = Form(""),
    cert_purpose: str = Form(""),
    cert_date: str = Form(""),
    cert_place: str = Form(""),
    additional_conditions: str = Form(""),
):
    row = db.get(LocationalClearanceCase, case_id)
    if not row:
        raise HTTPException(status_code=404)
    t = (lc_application_id or "").strip()
    new_la_id: int | None = int(t) if t.isdigit() else None
    la_row: LCApplication | None = None
    if new_la_id is not None:
        la_row = (
            db.scalars(
                select(LCApplication)
                .where(LCApplication.id == new_la_id)
                .options(joinedload(LCApplication.applicant))
            )
            .unique()
            .first()
        )
        if la_row is None:
            new_la_id = None
        elif not lc_application_allows_lc_prefill(la_row.lc_status):
            raise HTTPException(
                status_code=400,
                detail="Fee application must have LC status Paid before linking to an LC case.",
            )
    locked = new_la_id is not None and la_row is not None
    if locked:
        try:
            fix = _locked_form_strings_from_fee_la(la_row)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        application_number = fix["application_number"]
        date_of_receipt = fix["date_of_receipt"]
        or_date = fix["or_date"]
        amount_paid = fix["amount_paid"]
        applicant_address = fix["applicant_address"]
        corporation_address = fix["corporation_address"]
        project_title = fix["project_title"]
        project_location = fix["project_location"]
        lot_area_sqm = fix["lot_area_sqm"]
        project_cost_amount = fix["project_cost_amount"]
        applicant_first_name = fix["applicant_first_name"]
        applicant_last_name = fix["applicant_last_name"]
        applicant_middle_name = fix["applicant_middle_name"]
        applicant_suffix = fix["applicant_suffix"]
        ap = la_row.applicant
        if ap is None:
            raise HTTPException(status_code=400, detail="Fee application has no applicant record.")
        row.applicant_id = ap.id
    else:
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
        row.applicant_id = ap.id
    row.lc_application_id = new_la_id
    _apply_form_to_case(
        row,
        application_number=application_number,
        date_of_receipt=date_of_receipt,
        or_number=or_number,
        or_date=or_date,
        amount_paid=amount_paid,
        corporation_name=corporation_name,
        applicant_address=applicant_address,
        corporation_address=corporation_address,
        authorized_representative_name=authorized_representative_name,
        authorized_representative_address=authorized_representative_address,
        project_title=project_title,
        project_location=project_location,
        lot_area_sqm=lot_area_sqm,
        building_area_sqm=building_area_sqm,
        project_nature=project_nature,
        project_nature_other=project_nature_other,
        right_over_land=right_over_land,
        right_over_land_other=right_over_land_other,
        land_use_duration=land_use_duration,
        existing_land_use=existing_land_use,
        project_cost_words=project_cost_words,
        project_cost_amount=project_cost_amount,
        lc_notice_required=lc_notice_required,
        lc_notice_dates_filed=lc_notice_dates_filed,
        lc_notice_actions=lc_notice_actions,
        release_mode=release_mode,
        release_mail_to=release_mail_to,
        decision_number=decision_number,
        decision_date=decision_date,
        decision_outcome=decision_outcome,
        decision_headline=decision_headline,
        tct_oct_number=tct_oct_number,
        zoning_classification=zoning_classification,
        cert_parcel_location=cert_parcel_location,
        cert_area_words=cert_area_words,
        cert_registered_owner=cert_registered_owner,
        cert_lot_numbers=cert_lot_numbers,
        cert_issued_to=cert_issued_to,
        cert_purpose=cert_purpose,
        cert_date=cert_date,
        cert_place=cert_place,
        additional_conditions=additional_conditions,
    )
    db.commit()
    return RedirectResponse(url=f"/locational-clearance/{case_id}", status_code=303)


def _get_case_or_404(db: Session, case_id: int) -> LocationalClearanceCase:
    row = (
        db.scalars(
            select(LocationalClearanceCase)
            .where(LocationalClearanceCase.id == case_id)
            .options(joinedload(LocationalClearanceCase.applicant))
        )
        .unique()
        .first()
    )
    if not row:
        raise HTTPException(status_code=404)
    return row


@router.get("/{case_id}/print/application", response_class=HTMLResponse)
def print_application(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_locational_clearance_read),
):
    row = _get_case_or_404(db, case_id)
    return templates.TemplateResponse(
        request,
        "locational_clearance/print_application.html",
        {
            "c": row,
            "print_branding": get_print_profile(PRINT_PROFILE_LC),
        },
    )


@router.get("/{case_id}/print/decision", response_class=HTMLResponse)
def print_decision(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_locational_clearance_read),
):
    row = _get_case_or_404(db, case_id)
    return templates.TemplateResponse(
        request,
        "locational_clearance/print_decision.html",
        {
            "c": row,
            "print_branding": get_print_profile(PRINT_PROFILE_LC),
        },
    )


@router.get("/{case_id}/print/certification", response_class=HTMLResponse)
def print_certification(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_locational_clearance_read),
):
    row = _get_case_or_404(db, case_id)
    return templates.TemplateResponse(
        request,
        "locational_clearance/print_certification.html",
        {
            "c": row,
            "print_branding": get_print_profile(PRINT_PROFILE_LC),
        },
    )
