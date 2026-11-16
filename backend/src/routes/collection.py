from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from src.config.database import get_db
from src.controllers.dependencies import current_user,writers
from src.schemas.collection import VolumeOpen,AppendInput,ResumeInput
from src.services import collection
router=APIRouter()
@router.get('/collection/volumes')
def volumes(db:Session=Depends(get_db),user=Depends(current_user)):return collection.list_volumes(db)
@router.post('/collection/volumes')
def open(data:VolumeOpen,db:Session=Depends(get_db),user=Depends(writers)):return collection.open_volume(db,data,user.email)
@router.post('/collection/appends')
def append(data:AppendInput,db:Session=Depends(get_db),user=Depends(writers)):return collection.append_chunk(db,data,user.email)
@router.post('/collection/volumes/{id}/seal')
def seal(id:int,db:Session=Depends(get_db),user=Depends(writers)):return collection.seal_volume(db,id,user.email)
@router.post('/collection/volumes/{id}/pause')
def pause(id:int,db:Session=Depends(get_db),user=Depends(writers)):return collection.pause_volume(db,id,user.email)
@router.post('/collection/volumes/{id}/resume')
def resume(id:int,data:ResumeInput,db:Session=Depends(get_db),user=Depends(writers)):return collection.resume_volume(db,id,data,user.email)
@router.get('/collection/quarantine')
def quarantine(db:Session=Depends(get_db),user=Depends(current_user)):return collection.list_quarantine(db)
@router.get('/collection/ingest')
def ingest(db:Session=Depends(get_db),user=Depends(current_user)):return collection.list_ingest(db)
