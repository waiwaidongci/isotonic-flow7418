from pydantic import BaseModel,Field
class VolumeOpen(BaseModel):
 study_id:int
 volume_key:str=Field(min_length=1,max_length=180)
 generation:int=Field(ge=0,le=1000000)
 identity:str=Field(min_length=1,max_length=120)
class AppendInput(BaseModel):
 volume_key:str=Field(min_length=1,max_length=180)
 generation:int=Field(ge=0,le=1000000)
 identity:str=Field(min_length=1,max_length=120)
 base_offset:int=Field(ge=0)
 chunk_id:str=Field(min_length=1,max_length=120)
 data_b64:str=Field(max_length=1400000)
class ResumeInput(BaseModel):
 offset:int|None=Field(default=None,ge=0)
