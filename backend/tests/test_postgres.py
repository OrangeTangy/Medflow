"""Run against a disposable migrated PostgreSQL DB, never a hospital database."""
import os
from datetime import timedelta
import pytest
from sqlalchemy import create_engine,text,select
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError,IntegrityError
from app.models import *
from app.db import tenant_context
from app.services import rebuild,dashboard
from app.security import Principal

@pytest.fixture
def pg():
    url=os.getenv('TEST_POSTGRES_URL')
    if not url:pytest.skip('TEST_POSTGRES_URL is not configured')
    engine=create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='medflow_rls_test') THEN CREATE ROLE medflow_rls_test NOLOGIN NOBYPASSRLS; END IF; END $$"))
        conn.execute(text('GRANT USAGE ON SCHEMA public TO medflow_rls_test'))
        conn.execute(text('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO medflow_rls_test'))
    with Session(engine,expire_on_commit=False) as db:
        # All setup rolls back after each test.
        db.add_all([Organization(id='test-a',name='Test A'),Organization(id='test-b',name='Test B')]);db.flush()
        db.add_all([User(id='test-jane',organization_id='test-a',full_name='Jane',email='jane@test.example',role='doctor'),User(id='test-peer',organization_id='test-a',full_name='Peer',email='peer@test.example',role='doctor'),User(id='test-foreign',organization_id='test-b',full_name='Foreign',email='foreign@test.example',role='doctor')]);db.flush()
        db.add_all([Location(id='test-main',organization_id='test-a',name='Main',timezone='America/New_York'),Location(id='test-other',organization_id='test-b',name='Foreign')]);db.flush()
        db.add_all([ActivityReport(id='test-own',organization_id='test-a',doctor_id='test-jane',original_transcript='own',edited_transcript='own',category='Other'),ActivityReport(id='test-private',organization_id='test-a',doctor_id='test-peer',original_transcript='private',edited_transcript='private',category='Other'),ActivityReport(id='test-foreign-report',organization_id='test-b',doctor_id='test-foreign',original_transcript='foreign',edited_transcript='foreign',category='Other')]);db.flush()
        yield db
        db.rollback()
    engine.dispose()

def role(db,uid='test-jane',role='doctor'):
    db.execute(text('SET LOCAL ROLE medflow_rls_test'));tenant_context(db,'test-a',uid,role)
def test_rls_raw_select_does_not_leak_peer_or_tenant(pg):
    role(pg);assert {r.id for r in pg.scalars(select(ActivityReport))}=={'test-own'}
def test_rls_admin_is_still_organization_scoped(pg):
    role(pg,'test-jane','admin');assert {r.id for r in pg.scalars(select(ActivityReport))}=={'test-own','test-private'}
def test_rls_raw_update_cannot_modify_another_doctor(pg):
    role(pg);assert pg.execute(text("UPDATE activity_reports SET edited_transcript='tampered' WHERE id='test-private'")).rowcount==0
def test_rls_rejects_forged_doctor_insert(pg):
    role(pg)
    with pytest.raises(DBAPIError),pg.begin_nested():
        pg.add(ActivityReport(organization_id='test-a',doctor_id='test-peer',original_transcript='forged',edited_transcript='forged',category='Other'));pg.flush()
def test_rls_doctor_cannot_promote_self(pg):
    role(pg)
    with pytest.raises(DBAPIError),pg.begin_nested():pg.execute(text("UPDATE users SET role='admin' WHERE id='test-jane'"))
def test_no_context_defaults_to_no_access(pg):
    pg.execute(text('SET LOCAL ROLE medflow_rls_test'));assert list(pg.scalars(select(ActivityReport)))==[]
def test_cross_tenant_foreign_key_rejected(pg):
    with pytest.raises(IntegrityError),pg.begin_nested():
        pg.add(AttendanceSession(organization_id='test-a',doctor_id='test-jane',location_id='test-other',started_at=now(),ended_at=now()+timedelta(hours=1),duration_seconds=3600));pg.flush()
def test_database_exclusion_prevents_double_counting(pg):
    t=now()
    with pytest.raises(IntegrityError),pg.begin_nested():
        pg.add_all([AttendanceSession(organization_id='test-a',doctor_id='test-jane',location_id='test-main',started_at=t,ended_at=t+timedelta(hours=1),duration_seconds=3600),AttendanceSession(organization_id='test-a',doctor_id='test-jane',location_id='test-main',started_at=t+timedelta(minutes=30),ended_at=t+timedelta(hours=2),duration_seconds=5400)]);pg.flush();pg.execute(text('SET CONSTRAINTS no_overlapping_attendance IMMEDIATE'))
def test_rebuild_and_dashboard_execute_on_postgres(pg):
    d=Device(id='test-device',organization_id='test-a',doctor_id='test-jane',device_identifier='certificate',identity_reference='enrolled');n=WifiNetwork(id='test-network',organization_id='test-a',location_id='test-main',ssid='Enterprise',controller_identifier='controller');pg.add_all([d,n]);pg.flush()
    t=now()-timedelta(minutes=10)
    pg.add(NetworkEvent(organization_id='test-a',doctor_id='test-jane',device_id=d.id,network_id=n.id,location_id='test-main',event_type='start',source_event_id='start',accounting_session_id='one',event_timestamp=t,provider='radius'));pg.flush();rebuild(pg,'test-a','test-jane');pg.flush()
    data=dashboard(pg,Principal('test-jane','test-a','doctor'));assert len(data['doctors'])==1;assert data['doctors'][0]['status']=='Present';assert data['doctors'][0]['hours']>0
