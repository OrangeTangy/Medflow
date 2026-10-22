from datetime import datetime, timezone
from typing import Protocol
from pydantic import BaseModel, Field, field_validator

class NormalizedEvent(BaseModel):
    source_event_id:str=Field(min_length=1,max_length=200)
    identity_reference:str=Field(min_length=1,max_length=250)
    device_identifier:str=Field(min_length=1,max_length=150)
    controller_identifier:str=Field(min_length=1,max_length=150)
    accounting_session_id:str=Field(min_length=1,max_length=200)
    event_type:str
    event_timestamp:datetime
    @field_validator('event_type')
    @classmethod
    def valid_type(cls,v):
        if v not in ('start','stop','interim','outage'):raise ValueError('Unsupported accounting event')
        return v
    @field_validator('event_timestamp')
    @classmethod
    def aware(cls,v):
        if v.tzinfo is None:raise ValueError('UTC offset required')
        return v.astimezone(timezone.utc)

class ProviderAdapter(Protocol):
    def normalize(self,payload:dict)->NormalizedEvent: ...

class RadiusAdapter:
    """Trusted RADIUS sidecar posts JSON accounting attributes after 802.1X auth.
    EAP-Identity is the enrolled certificate/IdP identity, never Calling-Station-Id.
    Vendor integrations implement this same normalization contract.
    """
    def normalize(self,p):
        event_type={'Start':'start','Stop':'stop','Interim-Update':'interim'}[p['Acct-Status-Type']]
        return NormalizedEvent(source_event_id=p['Event-Id'],identity_reference=p['EAP-Identity'],device_identifier=p['Device-Certificate-Id'],controller_identifier=p['NAS-Identifier'],accounting_session_id=p['Acct-Session-Id'],event_type=event_type,event_timestamp=p['Event-Timestamp'])

class NormalizedWebhookAdapter:
    def normalize(self,p):return NormalizedEvent.model_validate(p)

ADAPTERS={'radius':RadiusAdapter(),'normalized':NormalizedWebhookAdapter()}
