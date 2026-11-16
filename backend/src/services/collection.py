import base64,binascii,math
from datetime import datetime,timezone
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from src.models import FlowStudy,DoseLevel,PressureReading,LogVolume,LogChunk,LogQuarantine,LogIngest
from .audit import record

MAX_CHUNK=1024*1024

def now():return datetime.now(timezone.utc)

def volume_dict(volume,stored=0,quarantined=0,chunks=0):
 pending=volume.pending or b''
 return {'id':volume.id,'study_id':volume.study_id,'volume_key':volume.volume_key,'generation':volume.generation,'identity':volume.identity,'offset':volume.offset,'lines':volume.lines,'status':volume.status,'error':volume.error,'pending_bytes':len(pending),'pending_preview':pending.decode('utf-8','replace'),'stored':stored,'quarantined':quarantined,'chunks':chunks,'created_at':volume.created_at.isoformat(),'updated_at':volume.updated_at.isoformat()}

def list_volumes(db):
 volumes=db.scalars(select(LogVolume).order_by(LogVolume.volume_key,LogVolume.generation)).all()
 stored=dict(db.execute(select(LogIngest.volume_id,func.count()).group_by(LogIngest.volume_id)).all())
 quarantined=dict(db.execute(select(LogQuarantine.volume_id,func.count()).group_by(LogQuarantine.volume_id)).all())
 chunks=dict(db.execute(select(LogChunk.volume_id,func.count()).group_by(LogChunk.volume_id)).all())
 return [volume_dict(v,stored.get(v.id,0),quarantined.get(v.id,0),chunks.get(v.id,0)) for v in volumes]

def list_quarantine(db):
 rows=db.scalars(select(LogQuarantine).order_by(LogQuarantine.id.desc()).limit(200)).all()
 volumes={v.id:v for v in db.scalars(select(LogVolume)).all()}
 return [{'id':q.id,'volume_id':q.volume_id,'volume_key':volumes[q.volume_id].volume_key if q.volume_id in volumes else '?','generation':volumes[q.volume_id].generation if q.volume_id in volumes else 0,'line_no':q.line_no,'raw':q.raw,'reason':q.reason,'created_at':q.created_at.isoformat()} for q in rows]

def list_ingest(db):
 rows=db.scalars(select(LogIngest).order_by(LogIngest.id.desc()).limit(200)).all()
 readings={r.id:r for r in db.scalars(select(PressureReading)).all()}
 volumes={v.id:v for v in db.scalars(select(LogVolume)).all()}
 levels={l.id:l for l in db.scalars(select(DoseLevel)).all()}
 out=[]
 for item in rows:
  reading=readings.get(item.reading_id);volume=volumes.get(item.volume_id)
  if not reading or not volume:continue
  out.append({'id':item.id,'reading_id':item.reading_id,'volume_id':item.volume_id,'volume_key':volume.volume_key,'generation':volume.generation,'line_no':item.line_no,'chunk_id':item.chunk_id,'specimen_ref':reading.specimen_ref,'pressure':reading.pressure,'flow':levels[reading.level_id].flow if reading.level_id in levels else None,'created_at':item.created_at.isoformat()})
 return out

def lock_study(db,study_id):
 study=db.get(FlowStudy,study_id,with_for_update=True)
 if not study:raise HTTPException(404,'研究不存在')
 return study

def lock_volume(db,key,generation):
 return db.scalar(select(LogVolume).where(LogVolume.volume_key==key,LogVolume.generation==generation).with_for_update())

def open_volume(db,data,actor):
 lock_study(db,data.study_id)
 volume=lock_volume(db,data.volume_key,data.generation)
 if volume:
  if volume.identity!=data.identity:raise HTTPException(409,'同名同代卷身份不符；同名换卷须使用新代次')
  if volume.study_id!=data.study_id:raise HTTPException(409,'同名同代卷已登记在其他研究')
  return volume_dict(volume)
 volume=LogVolume(study_id=data.study_id,volume_key=data.volume_key,generation=data.generation,identity=data.identity)
 db.add(volume)
 try:db.commit()
 except IntegrityError:
  db.rollback();volume=lock_volume(db,data.volume_key,data.generation)
  if volume and volume.identity==data.identity:return volume_dict(volume)
  raise HTTPException(409,'同名同代卷身份不符；同名换卷须使用新代次')
 record(db,actor,'collection.volume_opened',{'volume_id':volume.id,'volume_key':volume.volume_key,'generation':volume.generation})
 return volume_dict(volume)

def parse_line(raw):
 try:text=raw.decode('utf-8')
 except UnicodeDecodeError:raise ValueError('记录不是合法UTF-8')
 text=text.strip()
 if not text:return None
 parts=[p.strip() for p in text.split(',')]
 if len(parts)not in(3,4):raise ValueError('须为 滤片编号,流速,压差[,说明] 三或四列')
 specimen=parts[0]
 if not 1<=len(specimen)<=80:raise ValueError('滤片编号长度须为1..80字符')
 try:flow=float(parts[1]);pressure=float(parts[2])
 except ValueError:raise ValueError('流速或压差不是数值')
 if not math.isfinite(flow)or not 0<=flow<=1000:raise ValueError('流速须有限且0..1000')
 if not math.isfinite(pressure)or not 0<=pressure<=1000000:raise ValueError('压差须有限且0..1000000')
 return specimen,flow,pressure,(parts[3] if len(parts)==4 else '')[:500]

def find_level(db,study_id,flow):
 level=db.scalar(select(DoseLevel).where(DoseLevel.study_id==study_id,DoseLevel.flow==flow))
 if level:return level
 base=f'采集档-{flow:g}';label=base;suffix=2
 while db.scalar(select(DoseLevel).where(DoseLevel.study_id==study_id,DoseLevel.label==label)):
  label=f'{base}#{suffix}';suffix+=1
 level=DoseLevel(study_id=study_id,label=label,flow=flow);db.add(level);db.flush()
 return level

def pause_locked(db,volume,actor,reason):
 volume.status='paused';volume.error=reason;volume.updated_at=now();db.commit()
 record(db,actor,'collection.paused',{'volume_id':volume.id,'reason':reason})

def append_chunk(db,data,actor):
 try:payload=base64.b64decode(data.data_b64,validate=True)
 except (binascii.Error,ValueError):raise HTTPException(422,'数据块须为base64编码的原始字节')
 if len(payload)>MAX_CHUNK:raise HTTPException(422,'单块不得超过1MiB')
 volume=db.scalar(select(LogVolume).where(LogVolume.volume_key==data.volume_key,LogVolume.generation==data.generation))
 if not volume:raise HTTPException(404,'卷未登记，请先开卷或换卷')
 lock_study(db,volume.study_id)
 volume=lock_volume(db,data.volume_key,data.generation)
 if volume.status=='sealed':raise HTTPException(409,'卷已封存；同名继续采集须换用新代次')
 if volume.status=='paused':raise HTTPException(409,f'卷已暂停：{volume.error}')
 if volume.identity!=data.identity:
  reason='卷身份不符：同名换卷须使用新代次';pause_locked(db,volume,actor,reason);raise HTTPException(409,reason)
 seen=db.scalar(select(LogChunk).where(LogChunk.volume_id==volume.id,LogChunk.chunk_id==data.chunk_id))
 if seen:
  if seen.base_offset!=data.base_offset or seen.length!=len(payload):raise HTTPException(409,'块标识与已应用块不一致')
  return {'volume_id':volume.id,'offset':seen.base_offset+seen.length,'lines':volume.lines,'stored':seen.stored,'quarantined':seen.quarantined,'pending_bytes':len(volume.pending or b''),'pending_preview':(volume.pending or b'').decode('utf-8','replace'),'duplicate':True,'status':volume.status}
 if data.base_offset!=volume.offset:
  kind='截断' if data.base_offset<volume.offset else '跳读'
  reason=f'字节进度不符（{kind}）：卷进度{volume.offset}字节，收到{data.base_offset}字节';pause_locked(db,volume,actor,reason);raise HTTPException(409,reason)
 buffer=(volume.pending or b'')+payload
 segments=buffer.split(b'\n')
 volume.pending=segments[-1]
 stored=quarantined=0
 for raw in segments[:-1]:
  volume.lines+=1
  try:
   parsed=parse_line(raw)
   if parsed is None:continue
   specimen,flow,pressure,note=parsed
   if db.scalar(select(PressureReading.id).where(PressureReading.study_id==volume.study_id,PressureReading.specimen_ref==specimen)):raise ValueError('滤片编号在研究内重复，不作独立重复')
   level=find_level(db,volume.study_id,flow)
   reading=PressureReading(study_id=volume.study_id,level_id=level.id,specimen_ref=specimen,pressure=pressure,measurement_note=note or f'采集自{volume.volume_key}第{volume.lines}行')
   db.add(reading);db.flush()
   db.add(LogIngest(reading_id=reading.id,volume_id=volume.id,line_no=volume.lines,chunk_id=data.chunk_id))
   stored+=1
  except ValueError as error:
   db.add(LogQuarantine(volume_id=volume.id,line_no=volume.lines,raw=raw.decode('utf-8','replace'),reason=str(error)[:200]))
   quarantined+=1
 volume.offset=data.base_offset+len(payload);volume.updated_at=now()
 db.add(LogChunk(volume_id=volume.id,chunk_id=data.chunk_id,base_offset=data.base_offset,length=len(payload),stored=stored,quarantined=quarantined))
 try:db.commit()
 except IntegrityError:db.rollback();raise HTTPException(409,'采集并发冲突，请按当前卷进度重试')
 record(db,actor,'collection.appended',{'volume_id':volume.id,'chunk_id':data.chunk_id,'bytes':len(payload),'stored':stored,'quarantined':quarantined})
 return {'volume_id':volume.id,'offset':volume.offset,'lines':volume.lines,'stored':stored,'quarantined':quarantined,'pending_bytes':len(volume.pending),'pending_preview':volume.pending.decode('utf-8','replace'),'duplicate':False,'status':volume.status}

def locked_volume(db,id):
 volume=db.get(LogVolume,id)
 if not volume:raise HTTPException(404,'卷不存在')
 lock_study(db,volume.study_id)
 return db.get(LogVolume,id,with_for_update=True)

def seal_volume(db,id,actor):
 volume=locked_volume(db,id)
 if volume.status=='sealed':return volume_dict(volume)
 tail=None
 if volume.pending:
  tail=volume.pending.decode('utf-8','replace')
  db.add(LogQuarantine(volume_id=volume.id,line_no=None,raw=tail,reason='卷尾半条记录未补齐'))
  volume.pending=b''
 volume.status='sealed';volume.error=None;volume.updated_at=now();db.commit()
 record(db,actor,'collection.sealed',{'volume_id':volume.id,'tail_quarantined':bool(tail)})
 return volume_dict(volume)

def pause_volume(db,id,actor):
 volume=locked_volume(db,id)
 if volume.status!='active':raise HTTPException(409,'仅采集中的卷可人工暂停')
 pause_locked(db,volume,actor,'人工暂停')
 return volume_dict(volume)

def resume_volume(db,id,data,actor):
 volume=locked_volume(db,id)
 if volume.status!='paused':raise HTTPException(409,'仅暂停的卷可恢复')
 if data.offset is not None:
  if data.offset>volume.offset:raise HTTPException(422,'恢复点不能越过已存进度，不允许跳读')
  if data.offset<volume.offset:
   if volume.pending:
    db.add(LogQuarantine(volume_id=volume.id,line_no=None,raw=volume.pending.decode('utf-8','replace'),reason='回退重采，原半条记录隔离'))
    volume.pending=b''
   volume.offset=data.offset
 volume.status='active';volume.error=None;volume.updated_at=now();db.commit()
 record(db,actor,'collection.resumed',{'volume_id':volume.id,'offset':volume.offset})
 return volume_dict(volume)
