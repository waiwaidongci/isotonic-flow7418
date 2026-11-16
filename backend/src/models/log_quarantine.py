from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import ForeignKey,String,Integer,Text,DateTime
from datetime import datetime,timezone
from src.config.database import Base
class LogQuarantine(Base):
 __tablename__='log_quarantine'
 id:Mapped[int]=mapped_column(primary_key=True)
 volume_id:Mapped[int]=mapped_column(ForeignKey('log_volumes.id'))
 line_no:Mapped[int|None]=mapped_column(Integer,nullable=True)
 raw:Mapped[str]=mapped_column(Text)
 reason:Mapped[str]=mapped_column(String(200))
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
