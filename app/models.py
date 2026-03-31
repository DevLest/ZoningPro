from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    full_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    #: "admin" = full access; "staff" = access from role_permissions (staff row).
    role: Mapped[str] = mapped_column(String(32), default="staff", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role", "module_key", name="uq_role_module"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    module_key: Mapped[str] = mapped_column(String(64), index=True)
    can_read: Mapped[bool] = mapped_column(Boolean, default=True)
    can_write: Mapped[bool] = mapped_column(Boolean, default=False)


class Applicant(Base):
    """Reusable person record; multiple LC applications can reference one applicant."""

    __tablename__ = "applicants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(128), default="")
    last_name: Mapped[str] = mapped_column(String(128), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    suffix: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    applications: Mapped[list[LCApplication]] = relationship(back_populates="applicant")
    locational_clearance_cases: Mapped[list["LocationalClearanceCase"]] = relationship(back_populates="applicant")

    @property
    def display_name(self) -> str:
        from app.applicant_service import applicant_display_name  # noqa: PLC0415

        return applicant_display_name(self)


class LCApplication(Base):
    __tablename__ = "lc_applications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lc_ctrl_no: Mapped[str] = mapped_column(String(64), index=True)
    date_of_application: Mapped[date] = mapped_column(Date())
    applicant_id: Mapped[int] = mapped_column(ForeignKey("applicants.id"), index=True)
    applicant: Mapped[Applicant] = relationship(back_populates="applications")
    address: Mapped[str] = mapped_column(String(512))
    #: From address autocomplete (Nominatim/Photon/Google) when the user picks a suggestion.
    address_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    address_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    project_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    project_location: Mapped[str | None] = mapped_column(String(512), nullable=True)
    doc_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    lc_status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    date_granted: Mapped[date | None] = mapped_column(Date(), nullable=True)
    lc_fees: Mapped[float | None] = mapped_column(Float, nullable=True)
    zc_fees: Mapped[float | None] = mapped_column(Float, nullable=True)
    surcharge: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)

    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    lot_area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    optional_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: JSON array of {"name": str, "price": float} — itemized surcharge lines.
    surcharge_items: Mapped[str | None] = mapped_column(Text, nullable=True)
    surcharge_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    lc_fee_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    waive_zoning_cert: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    locational_clearance_cases: Mapped[list["LocationalClearanceCase"]] = relationship(back_populates="lc_application")

    @property
    def applicant_display_name(self) -> str:
        if self.applicant is None:
            return "—"
        return self.applicant.display_name


class LocationalClearanceCase(Base):
    """LC Form 1 (application), Form 2 (decision), and Form 03 (zoning certification) — one saved case."""

    __tablename__ = "locational_clearance_cases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    applicant_id: Mapped[int] = mapped_column(ForeignKey("applicants.id"), index=True)
    applicant: Mapped[Applicant] = relationship(back_populates="locational_clearance_cases")
    #: Optional link to an LC fee/estimate record when the same project exists in both workflows.
    lc_application_id: Mapped[int | None] = mapped_column(ForeignKey("lc_applications.id"), nullable=True, index=True)
    lc_application: Mapped[LCApplication | None] = relationship(back_populates="locational_clearance_cases")

    application_number: Mapped[str] = mapped_column(String(64), default="")
    date_of_receipt: Mapped[date | None] = mapped_column(Date(), nullable=True)
    or_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    or_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    amount_paid: Mapped[float | None] = mapped_column(Float, nullable=True)

    corporation_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    applicant_address: Mapped[str] = mapped_column(String(512), default="")
    corporation_address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    authorized_representative_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    authorized_representative_address: Mapped[str | None] = mapped_column(String(512), nullable=True)

    project_title: Mapped[str] = mapped_column(String(512), default="")
    project_location: Mapped[str | None] = mapped_column(String(512), nullable=True)
    lot_area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    building_area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)

    #: new_development | improvement | others
    project_nature: Mapped[str | None] = mapped_column(String(32), nullable=True)
    project_nature_other: Mapped[str | None] = mapped_column(String(256), nullable=True)
    #: owner | lessee | other
    right_over_land: Mapped[str | None] = mapped_column(String(32), nullable=True)
    right_over_land_other: Mapped[str | None] = mapped_column(String(256), nullable=True)
    #: permanent | temporary
    land_use_duration: Mapped[str | None] = mapped_column(String(32), nullable=True)

    existing_land_use: Mapped[str | None] = mapped_column(String(256), nullable=True)
    project_cost_words: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_cost_amount: Mapped[float | None] = mapped_column(Float, nullable=True)

    lc_notice_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    lc_notice_dates_filed: Mapped[str | None] = mapped_column(String(256), nullable=True)
    lc_notice_actions: Mapped[str | None] = mapped_column(String(512), nullable=True)

    #: pickup | mail
    release_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: applicant | authorized_rep (when release_mode is mail)
    release_mail_to: Mapped[str | None] = mapped_column(String(32), nullable=True)

    decision_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    #: granted | denied
    decision_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision_headline: Mapped[str | None] = mapped_column(String(256), nullable=True)

    tct_oct_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    zoning_classification: Mapped[str | None] = mapped_column(String(128), nullable=True)

    cert_parcel_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    cert_area_words: Mapped[str | None] = mapped_column(String(256), nullable=True)
    cert_registered_owner: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cert_lot_numbers: Mapped[str | None] = mapped_column(String(256), nullable=True)
    cert_issued_to: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cert_purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    cert_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    cert_place: Mapped[str | None] = mapped_column(String(256), nullable=True)

    additional_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def applicant_line(self) -> str:
        """Line for Form 1/2 field 1 — natural person or organization from applicant record."""
        if self.applicant is None:
            return ""
        return self.applicant.display_name

    @property
    def corporation_line(self) -> str:
        return (self.corporation_name or "").strip() or self.applicant_line
