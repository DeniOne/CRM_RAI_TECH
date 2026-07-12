import enum
from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import String, Text, Boolean, Float, Integer, ForeignKey, func, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    manager = "manager"
    supervisor = "supervisor"
    admin = "admin"


class InvitePurpose(str, enum.Enum):
    invite = "invite"
    reset = "reset"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.manager)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    leads: Mapped[List["Lead"]] = relationship(back_populates="region")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    region_id: Mapped[Optional[int]] = mapped_column(ForeignKey("regions.id"), nullable=True)
    assigned_manager_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Company info
    name: Mapped[str] = mapped_column(String(500), index=True)
    district: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    settlement: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    inn: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    head_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    site: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Юридические реквизиты
    ogrn: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    kpp: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    okpo: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    legal_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    postal_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    bank_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    bank_bic: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    bank_account: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    bank_corr_account: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # Rapeseed
    rapeseed_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rapeseed_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    rapeseed_volume: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    harvest_timing: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Funnel
    level: Mapped[Optional[str]] = mapped_column(String(1), nullable=True)  # A/B/C
    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1/2/3
    stage: Mapped[str] = mapped_column(String(10), default="0")  # 0..7, lost
    stage_changed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    loss_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Notes
    general_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    done_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    todo_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Relationships
    region: Mapped[Optional["Region"]] = relationship(back_populates="leads")
    assigned_manager: Mapped[Optional["User"]] = relationship()
    contacts: Mapped[List["Contact"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    contact_logs: Mapped[List["ContactLog"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    comments: Mapped[List["Comment"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    tasks: Mapped[List["Task"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    deals: Mapped[List["Deal"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    documents: Mapped[List["Document"]] = relationship(back_populates="lead", cascade="all, delete-orphan")


class StageHistory(Base):
    __tablename__ = "stage_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"))
    from_stage: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(10))
    changed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"))
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    position: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[str] = mapped_column(String(100))
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_decision_maker: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    lead: Mapped["Lead"] = relationship(back_populates="contacts")


class ContactLog(Base):
    __tablename__ = "contact_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"))
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    contact_type: Mapped[str] = mapped_column(String(20), default="call")
    contact_date: Mapped[datetime] = mapped_column()
    result: Mapped[str] = mapped_column(Text)
    outcome: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    next_action_date: Mapped[Optional[date]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    lead: Mapped["Lead"] = relationship(back_populates="contact_logs")


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    lead: Mapped["Lead"] = relationship(back_populates="comments")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lead_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leads.id"), nullable=True)
    assigned_to: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=2)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    lead: Mapped[Optional["Lead"]] = relationship(back_populates="tasks")


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(500))
    amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="new")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    closed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    lead: Mapped["Lead"] = relationship(back_populates="deals")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    deal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deals.id"), nullable=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    doc_type: Mapped[str] = mapped_column(String(20))
    template_id: Mapped[Optional[int]] = mapped_column(ForeignKey("document_templates.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_path_pdf: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    sent_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    lead: Mapped["Lead"] = relationship(back_populates="documents")


class DocumentTemplate(Base):
    __tablename__ = "document_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    doc_type: Mapped[str] = mapped_column(String(20))
    file_path: Mapped[str] = mapped_column(String(500))
    placeholders: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    context_lead_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leads.id"), nullable=True)
    actions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped["User"] = relationship()


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.manager)
    purpose: Mapped[InvitePurpose] = mapped_column(SAEnum(InvitePurpose), default=InvitePurpose.invite)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column()
    used_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)


class LibraryFolder(Base):
    """Папка в библиотеке. parent_id=None — корень. Дерево в БД, не на диске."""
    __tablename__ = "library_folders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("library_folders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    parent: Mapped[Optional["LibraryFolder"]] = relationship(
        remote_side="LibraryFolder.id", back_populates="children"
    )
    children: Mapped[List["LibraryFolder"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    files: Mapped[List["LibraryFile"]] = relationship(
        back_populates="folder", cascade="all, delete-orphan"
    )


class LibraryFile(Base):
    """Файл в библиотеке. Физически лежит в storage/library/, путь — в file_path."""
    __tablename__ = "library_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    folder_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("library_folders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))  # отображаемое имя (без uid)
    original_filename: Mapped[str] = mapped_column(String(500))
    extension: Mapped[str] = mapped_column(String(20), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    file_path: Mapped[str] = mapped_column(String(500))  # путь к физическому файлу
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    folder: Mapped[Optional["LibraryFolder"]] = relationship(back_populates="files")
