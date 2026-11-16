from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import ForeignKey,String,Integer,BigInteger,DateTime,UniqueConstraint
from datetime import datetime,timezone
from src.config.database import Base
class LogChunk(Base):
 __tablename__='log_chunks'
 __table_args__=(UniqueConstraint('volume_id','chunk_id'),)
 id:Mapped[int]=mapped_column(primary_key=True)
 volume_id:Mapped[int]=mapped_column(ForeignKey('log_volumes.id'))
 chunk_id:Mapped[str]=mapped_column(String(120))
 base_offset:Mapped[int]=mapped_column(BigInteger)
 length:Mapped[int]=mapped_column(Integer)
 stored:Mapped[int]=mapped_column(Integer,default=0)
 quarantined:Mapped[int]=mapped_column(Integer,default=0)
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
