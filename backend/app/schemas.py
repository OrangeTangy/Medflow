from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')
class ReportInput(Strict):
    original_transcript:str=Field(min_length=1,max_length=100000)
    edited_transcript:str=Field(min_length=1,max_length=100000)
    category:Literal['Patient Care','Consultations','Administrative Duties','Surgery / Procedures','Meetings','Research','Teaching','Other']
    location_id:str|None=None
    tags:list[str]=Field(default_factory=list,max_length=20)
class UserInput(Strict):
    full_name:str=Field(min_length=2,max_length=100)
    email:str=Field(pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$',max_length=254)
    department:str=Field(min_length=1,max_length=100)
    identity_reference:str=Field(min_length=1,max_length=250)
class LocationInput(Strict):
    name:str=Field(min_length=2,max_length=100)
    building:str=Field(default='',max_length=150)
    timezone:str='UTC'
    ssid:str=Field(min_length=1,max_length=100)
    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls,v):
        try:ZoneInfo(v)
        except ZoneInfoNotFoundError:raise ValueError('Unknown IANA timezone')
        return v
class Changes(Strict):
    started_at:datetime
    ended_at:datetime
    location_id:str
    @model_validator(mode='after')
    def ordered(self):
        if self.started_at.tzinfo is None or self.ended_at.tzinfo is None:raise ValueError('Timezone offsets required')
        if self.ended_at<=self.started_at or (self.ended_at-self.started_at).total_seconds()>86400:raise ValueError('Correction must be a positive period of no more than 24 hours')
        return self
class CorrectionInput(Strict):
    session_id:str|None=None
    requested_changes:Changes
    reason:str=Field(min_length=10,max_length=2000)
class Decision(Strict):
    decision:Literal['approved','rejected']
class CheckinInput(Strict):
    location_id:str
    action:Literal['start','stop']
    reason:str=Field(min_length=5,max_length=2000)
class ProfileInput(Strict):
    full_name:str=Field(min_length=2,max_length=100)
    notifications:bool=True
