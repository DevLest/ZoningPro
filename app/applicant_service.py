"""Applicants (reusable customer records) and intake resolution."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Applicant, LCApplication


def applicant_display_name(applicant: Applicant) -> str:
    parts: list[str] = []
    if applicant.first_name and applicant.first_name.strip():
        parts.append(applicant.first_name.strip())
    if applicant.middle_name and applicant.middle_name.strip():
        parts.append(applicant.middle_name.strip())
    if applicant.last_name and applicant.last_name.strip():
        parts.append(applicant.last_name.strip())
    suf = (applicant.suffix or "").strip()
    if suf:
        parts.append(suf)
    return " ".join(parts) if parts else "—"


def resolve_applicant_for_intake(
    db: Session,
    *,
    existing_applicant_id: str,
    first_name: str,
    last_name: str,
    middle_name: str,
    suffix: str,
) -> Applicant:
    """Link to an existing applicant id when provided; otherwise create a new row."""
    fn = first_name.strip()
    ln = last_name.strip()
    if not fn:
        raise ValueError("First name is required.")
    if not ln:
        raise ValueError("Last name is required.")

    eid = (existing_applicant_id or "").strip()
    if eid.isdigit():
        ap = db.get(Applicant, int(eid))
        if ap is not None:
            ap.first_name = fn
            ap.last_name = ln
            ap.middle_name = middle_name.strip() or None
            ap.suffix = suffix.strip() or None
            return ap

    ap = Applicant(
        first_name=fn,
        last_name=ln,
        middle_name=middle_name.strip() or None,
        suffix=suffix.strip() or None,
    )
    db.add(ap)
    db.flush()
    return ap


def list_applicants_for_directory(db: Session, q: str | None, *, limit: int = 500) -> list[Applicant]:
    """All applicants (ordered), optionally filtered by a name substring."""
    stmt = select(Applicant).order_by(Applicant.last_name, Applicant.first_name)
    qs = (q or "").strip()
    if len(qs) >= 1:
        pat = f"%{qs}%"
        stmt = stmt.where(
            or_(
                Applicant.first_name.like(pat),
                Applicant.last_name.like(pat),
                Applicant.middle_name.like(pat),
                Applicant.suffix.like(pat),
            )
        )
    stmt = stmt.limit(limit)
    return list(db.scalars(stmt).all())


def search_applicants_for_suggest(db: Session, q: str, *, limit: int = 12) -> list[Applicant]:
    q = (q or "").strip()
    if len(q) < 2:
        return []
    pat = f"%{q}%"
    stmt = (
        select(Applicant)
        .where(
            or_(
                Applicant.first_name.like(pat),
                Applicant.last_name.like(pat),
                Applicant.middle_name.like(pat),
                Applicant.suffix.like(pat),
            )
        )
        .order_by(Applicant.last_name, Applicant.first_name)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def applicant_suggestion_dicts(db: Session, applicants: list[Applicant]) -> list[dict]:
    if not applicants:
        return []
    ids = [a.id for a in applicants]
    cnt_rows = db.execute(
        select(LCApplication.applicant_id, func.count(LCApplication.id))
        .where(LCApplication.applicant_id.in_(ids))
        .group_by(LCApplication.applicant_id)
    ).all()
    counts = {int(r[0]): int(r[1]) for r in cnt_rows}
    out: list[dict] = []
    for ap in applicants:
        aid = ap.id
        n = counts.get(aid, 0)
        recent = db.scalar(
            select(LCApplication.lc_ctrl_no)
            .where(LCApplication.applicant_id == aid)
            .order_by(LCApplication.created_at.desc())
            .limit(1)
        )
        out.append(
            {
                "id": aid,
                "display_name": applicant_display_name(ap),
                "first_name": ap.first_name or "",
                "last_name": ap.last_name or "",
                "middle_name": ap.middle_name or "",
                "suffix": ap.suffix or "",
                "application_count": n,
                "recent_ctrl_no": recent,
            }
        )
    return out
