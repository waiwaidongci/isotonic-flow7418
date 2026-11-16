from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import ForeignKey,String,Integer,BigInteger,LargeBinary,Text,DateTime,UniqueConstraint
from datetime import datetime,timezone
from src.config.database import Base
class LogVolume(Base):
 __tablename__='log_volumes'
 __table_args__=(UniqueConstraint('volume_key','generation'),)
 id:Mapped[int]=mapped_column(primary_key=True)
 study_id:Mapped[int]=mapped_column(ForeignKey('flow_studies.id'))
 volume_key:Mapped[str]=mapped_column(String(180))
 generation:Mapped[int]=mapped_column(Integer)
 identity:Mapped[str]=mapped_column(String(120))
 offset:Mapped[int]=mapped_column(BigInteger,default=0)
 lines:Mapped[int]=mapped_column(Integer,default=0)
 pending:Mapped[bytes]=mapped_column(LargeBinary,default=b'')
 status:Mapped[str]=mapped_column(String(16),default='active')
 error:Mapped[str|None]=mapped_column(Text,nullable=True)
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
 updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
