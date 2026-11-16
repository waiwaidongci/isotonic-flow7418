from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import ForeignKey,String,Integer,DateTime
from datetime import datetime,timezone
from src.config.database import Base
class LogIngest(Base):
 __tablename__='log_ingest'
 id:Mapped[int]=mapped_column(primary_key=True)
 reading_id:Mapped[int]=mapped_column(ForeignKey('pressure_readings.id'),unique=True)
 volume_id:Mapped[int]=mapped_column(ForeignKey('log_volumes.id'))
 line_no:Mapped[int]=mapped_column(Integer)
 chunk_id:Mapped[str]=mapped_column(String(120))
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
