import enum
from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import String, Text, Boolean, Float, Integer, Numeric, ForeignKey, UniqueConstraint, func, Enum as SAEnum
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
    # IANA-имя часового пояса (Europe/Moscow, Asia/Vladivostok…).
    # NULL → код трактует как DEFAULT_TZ (Europe/Moscow).
    timezone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
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

    # Связь с опциональным комментарием и задачей в едином Журнале
    comment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("comments.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )

    lead: Mapped["Lead"] = relationship(back_populates="contact_logs")
    user: Mapped[Optional["User"]] = relationship(foreign_keys=[user_id])
    comment: Mapped[Optional["Comment"]] = relationship(foreign_keys=[comment_id])
    task: Mapped[Optional["Task"]] = relationship(foreign_keys=[task_id])


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    lead: Mapped["Lead"] = relationship(back_populates="comments")
    user: Mapped[Optional["User"]] = relationship(foreign_keys=[user_id])


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
    quote_id: Mapped[Optional[int]] = mapped_column(ForeignKey("quotes.id"), nullable=True)
    template_id: Mapped[Optional[int]] = mapped_column(ForeignKey("document_templates.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_path_pdf: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    sent_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    # Оплата счёта (фаза 21): проставляются при отметке оплаты
    paid_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    paid_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
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


class ProductCategory(Base):
    """Категория каталога. parent_id=None — корень. Дерево любой глубины:
    поставщики приходят с разной вложенностью (у АгроВиты — один уровень)."""
    __tablename__ = "product_categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("product_categories.id", ondelete="CASCADE"), nullable=True, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    parent: Mapped[Optional["ProductCategory"]] = relationship(
        remote_side="ProductCategory.id", back_populates="children"
    )
    children: Mapped[List["ProductCategory"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    products: Mapped[List["Product"]] = relationship(back_populates="category")


class Product(Base):
    """Товар каталога — только номенклатура. Цены живут в прайс-листах (фаза 18),
    позиции КП — в quote_items (фаза 19). attrs_json — гибкие характеристики
    (мощность, объём, состав), чтобы не ALTER'ить таблицу под каждый атрибут."""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("product_categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(512), index=True)
    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    unit: Mapped[str] = mapped_column(String(20), default="шт")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # resale — перепродажа (оборудование поставщика), own — собственный продукт (Грипил)
    origin: Mapped[str] = mapped_column(String(20), default="resale")
    # Имя файла в storage/catalog/images/ (без пути — URL строится /catalog/images/{file})
    image_file: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Страница товара на сайте производителя; в каталоге АгроВиты уникален — upsert-ключ
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, index=True)
    attrs_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    category: Mapped[Optional["ProductCategory"]] = relationship(back_populates="products")


class PriceList(Base):
    """Прайс-лист. В v2.0 один базовый (is_default); модель сразу под будущие
    сегментные/региональные списки (решение владельца: базовый прайс + скидка в КП)."""
    __tablename__ = "price_lists"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    prices: Mapped[List["ProductPrice"]] = relationship(back_populates="price_list")


class ProductPrice(Base):
    """Цена товара в прайс-листе. Цена не задана = «цена по запросу».
    min_qty заложен под будущие ступенчатые скидки, в UI v2.0 не используется."""
    __tablename__ = "product_prices"
    __table_args__ = (
        # один товар — одна цена в прайс-листе; upsert по этой паре
        UniqueConstraint("product_id", "price_list_id", name="uq_product_pricelist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    price_list_id: Mapped[int] = mapped_column(ForeignKey("price_lists.id", ondelete="CASCADE"), index=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    min_qty: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    product: Mapped["Product"] = relationship()
    price_list: Mapped["PriceList"] = relationship(back_populates="prices")


class SequenceCounter(Base):
    """Счётчик номеров документов (КП, счёт...) по годам. name+year уникальны."""
    __tablename__ = "sequence_counters"
    __table_args__ = (
        UniqueConstraint("name", "year", name="uq_counter_name_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50))
    year: Mapped[int] = mapped_column(Integer)
    value: Mapped[int] = mapped_column(Integer, default=0)


class Quote(Base):
    """Коммерческое предложение. Позиции — СНАПШОТ (name/price на момент КП):
    смена прайса не должна менять отправленные КП задним числом."""
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    number: Mapped[str] = mapped_column(String(30), unique=True, index=True)  # КП-2026-0001
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    deal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deals.id"), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # draft → sent → accepted | rejected; sent/rejected → draft (правка)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    valid_until: Mapped[Optional[date]] = mapped_column(nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    lead: Mapped["Lead"] = relationship()
    deal: Mapped[Optional["Deal"]] = relationship()
    user: Mapped["User"] = relationship()
    items: Mapped[List["QuoteItem"]] = relationship(
        back_populates="quote", cascade="all, delete-orphan", order_by="QuoteItem.sort_order"
    )


class QuoteItem(Base):
    """Позиция КП. product_id nullable — «своя позиция» (доставка, монтаж...).
    name/sku/unit/price — снапшот на момент добавления."""
    __tablename__ = "quote_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("quotes.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(512))
    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="шт")
    qty: Mapped[float] = mapped_column(Numeric(12, 3), default=1)
    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    discount_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    quote: Mapped["Quote"] = relationship(back_populates="items")


class CompanyProfile(Base):
    """Реквизиты продавца (singleton id=1) для печатных форм + настройки НДС и логотип."""
    __tablename__ = "company_profile"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), default="РАИ Технологии")
    inn: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    kpp: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ogrn: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    legal_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    site: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    bank_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    bank_bic: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    bank_account: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    bank_corr_account: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    director_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tax_note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # «Без НДС» / «НДС не облагается (УСН)»
    logo_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # имя файла в storage/company/
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class PrintTemplate(Base):
    """Редактируемые тексты печатных форм (kind='quote', позже 'invoice'/'contract').
    Текст с кириллическими плейсхолдерами {Менеджер}, {Клиент}...; рендер —
    словарная замена по экранированному тексту, НЕ Jinja (анти-RCE)."""
    __tablename__ = "print_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(20), unique=True)  # quote | invoice | contract
    intro: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # текст до таблицы
    conditions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # условия после таблицы
    signature: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # подпись
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
