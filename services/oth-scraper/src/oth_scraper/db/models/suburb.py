from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from oth_scraper.db.engine import Base


class Suburb(Base):
    __tablename__ = "suburb"
    __table_args__ = (
        UniqueConstraint("name", "postcode", "state", name="uq_suburb_name_postcode_state"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    postcode: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    oth_slug: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
