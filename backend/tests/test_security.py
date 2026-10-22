import os
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select,text
from sqlalchemy.orm import Session
from app.models import *
from app.security import Principal,principal,database
from app.main import app
from app.db import tenant_context
from app.services import get_record,scope
from app.schemas import ReportInput,Changes,LocationInput
from app.adapters import RadiusAdapter
from app.exports import csv_export,pdf_export

@pytest.fixture
def db():
    engine=create_engine('sqlite:///:memory:',connect_args={'check_same_thread':False},poolclass=__import__('sqlalchemy').pool.StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        db.add_all([Organization(id='a',name='A'),Organization(id='b',name='B')]);db.flush()
        db.add_all([User(id='doctor',organization_id='a',full_name='Jane',email='jane@a.test',role='doctor'),User(id='peer',organization_id='a',full_name='Peer',email='peer@a.test',role='doctor'),User(id='foreign',organization_id='b',full_name='Foreign',email='foreign@b.test',role='doctor'),User(id='admin',organization_id='a',full_name='Admin',email='admin@a.test',role='admin')]);db.flush()
        db.add_all([ActivityReport(id='own',organization_id='a',doctor_id='doctor',original_transcript='Original',edited_transcript='My report',category='Other'),ActivityReport(id='peer-report',organization_id='a',doctor_id='peer',original_transcript='Secret',edited_transcript='Peer private',category='Other'),ActivityReport(id='foreign-report',organization_id='b',doctor_id='foreign',original_transcript='Secret',edited_transcript='Other hospital',category='Other')]);db.commit();yield db
    engine.dispose()

@pytest.fixture
def client(db,monkeypatch):
    monkeypatch.setattr('app.main.rate_limit',lambda *a,**k:None)
    app.dependency_overrides[principal]=lambda:Principal('doctor','a','doctor')
    app.dependency_overrides[database]=lambda:db
    with TestClient(app,headers={'origin':'https://medflow.example.org'}) as c:yield c
    app.dependency_overrides.clear()

def test_doctor_list_is_own_only(client):
    r=client.get('/api/reports');assert r.status_code==200;assert [r['id'] for r in r.json()]==['own']
@pytest.mark.parametrize('rid',['peer-report','foreign-report','missing'])
def test_modified_report_urls_rejected(client,rid):assert client.get('/api/reports/'+rid).status_code==404
def test_doctor_admin_directory_rejected(client):assert client.get('/api/users').status_code==403
def test_doctor_other_user_rejected(client):assert client.get('/api/users/peer').status_code==404
def test_doctor_cannot_select_other_identity(client):assert client.get('/api/attendance?doctor_id=peer').status_code==403
def test_forged_report_doctor_id_rejected(client):
    r=client.post('/api/reports',json={'doctor_id':'peer','original_transcript':'a','edited_transcript':'b','category':'Other'});assert r.status_code==422
def test_cross_origin_mutation_rejected(client):
    assert client.post('/api/reports',headers={'origin':'https://attacker.test'},json={}).status_code==403
def test_report_creation_identity_bound_to_session(client,db):
    r=client.post('/api/reports',json={'original_transcript':'Original dictation','edited_transcript':'Reviewed dictation','category':'Other'});assert r.status_code==201;assert r.json()['doctor_id']=='doctor'
def test_original_transcript_is_immutable(client):
    r=client.patch('/api/reports/own',json={'original_transcript':'Tampered','edited_transcript':'Updated text','category':'Meetings'});assert r.status_code==200 and r.json()['original_transcript']=='Original'
def test_doctor_cannot_review_report(client):assert client.post('/api/reports/own/review',json={}).status_code==403
def test_unapproved_transcription_fail_closed(client):assert client.post('/api/transcriptions',files={'audio':('a.webm',b'audio','audio/webm')}).status_code==503
def test_organization_scope_applies_to_admin(db):
    p=Principal('admin','a','admin');assert {u.id for u in db.scalars(scope(User,p))}=={'doctor','peer','admin'}
def test_unauthenticated_request_fails(db,monkeypatch):
    app.dependency_overrides.clear();monkeypatch.setattr('app.main.rate_limit',lambda *a,**k:None)
    with TestClient(app) as c:assert c.get('/api/reports').status_code==401
def test_invalid_timezone_rejected():
    with pytest.raises(ValueError):LocationInput(name='Hospital',ssid='Enterprise',timezone='Invalid/Mars')
def test_invalid_correction_range_rejected():
    with pytest.raises(ValueError):Changes(started_at=now(),ended_at=now()-timedelta(hours=1),location_id='hospital')
def test_radius_requires_individual_identity():
    with pytest.raises(KeyError):RadiusAdapter().normalize({'Acct-Status-Type':'Start','Event-Id':'1'})
def test_csv_formula_injection_is_escaped():
    result=csv_export([{'full_name':'=HYPERLINK("evil")','department':'A','location':None,'first_arrival':None,'hours':1,'status':'No signal'}]);assert "'=HYPERLINK" in result
def test_pdf_is_real_document():
    assert pdf_export([],now().date()).startswith(b'%PDF-1.4')
