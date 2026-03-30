from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

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


class LCApplication(Base):
    __tablename__ = "lc_applications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lc_ctrl_no: Mapped[str] = mapped_column(String(64), index=True)
    date_of_application: Mapped[date] = mapped_column(Date())
    applicant_name: Mapped[str] = mapped_column(String(256))
    address: Mapped[str] = mapped_column(String(512))
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
    surcharge_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    lc_fee_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    waive_zoning_cert: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
