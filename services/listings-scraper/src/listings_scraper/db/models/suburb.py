from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from listings_scraper.db.engine import Base
from listings_scraper.vendor import Vendor

_vendor_enum = Enum("oth", "domain", name="vendor", create_type=False)


class Suburb(Base):
    __tablename__ = "suburb"
    __table_args__ = (
        UniqueConstraint(
            "source", "name", "postcode", "state",
            name="uq_suburb_source_name_postcode_state",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    postcode: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source: Mapped[Vendor] = mapped_column(
        _vendor_enum, nullable=False, default=Vendor.OTH
    )
