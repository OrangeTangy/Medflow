from datetime import datetime, timezone, timedelta, time
from zoneinfo import ZoneInfo
from sqlalchemy import select, delete, text
from .models import *
from .reconcile import Evidence,reconcile,clipped_seconds
from .db import tenant_context
from .config import settings

def audit(db,p,action,resource,resource_id=None,details=None):
    db.add(AuditLog(organization_id=p.organization_id,actor_id=p.id,action=action,resource_type=resource,resource_id=resource_id,details=details or {}))
def scope(model,p):
    q=select(model).where(model.organization_id==p.organization_id)
    if p.role!='admin' and hasattr(model,'doctor_id'):q=q.where(model.doctor_id==p.id)
    if p.role!='admin' and model is User:q=q.where(User.id==p.id)
    return q
def get_record(db,model,rid,p):
    from fastapi import HTTPException
    obj=db.scalar(scope(model,p).where(model.id==rid))
    if obj is None:raise HTTPException(404,'Record not found')
    return obj
def json_row(row):
    return {c.key:(getattr(row,c.key).isoformat() if isinstance(getattr(row,c.key),datetime) else getattr(row,c.key)) for c in row.__mapper__.column_attrs}
def lock_doctor(db,doctor_id):
    if db.bind.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:doctor,0))'),{'doctor':doctor_id})

def rebuild(db,org,doctor_id,as_of=None):
    as_of=as_of or now();lock_doctor(db,doctor_id)
    events=db.scalars(select(NetworkEvent).where(NetworkEvent.organization_id==org,NetworkEvent.doctor_id==doctor_id).order_by(NetworkEvent.event_timestamp)).all()
    periods=reconcile([Evidence(e.id,e.device_id,e.accounting_session_id,e.location_id,e.event_type,e.event_timestamp) for e in events],as_of,settings().presence_grace_seconds,settings().presence_stale_seconds)
    db.execute(delete(AttendanceSession).where(AttendanceSession.organization_id==org,AttendanceSession.doctor_id==doctor_id,AttendanceSession.source=='network'))
    fixed=db.scalars(select(AttendanceSession).where(AttendanceSession.organization_id==org,AttendanceSession.doctor_id==doctor_id,AttendanceSession.source!='network')).all()
    unknown=db.scalar(select(Location).where(Location.organization_id==org,Location.name=='Unknown / Transit'))
    if not unknown:
        unknown=Location(organization_id=org,name='Unknown / Transit',timezone='UTC',active=False);db.add(unknown);db.flush()
    for p in periods:
        segments=[(p.start,p.end)]
        for f in fixed:
            cut_end=f.ended_at or as_of
            segments=[part for a,b in segments for part in ([(a,b)] if b<=f.started_at or a>=cut_end else ([(a,f.started_at)] if a<f.started_at else [])+([(cut_end,b)] if b>cut_end else []))]
        for a,b in segments:
            if b<=a:continue
            db.add(AttendanceSession(organization_id=org,doctor_id=doctor_id,location_id=unknown.id if p.location_id=='unknown' else p.location_id,started_at=a,ended_at=None if p.ongoing and b==as_of else b,duration_seconds=int((b-a).total_seconds()),confidence_status=p.confidence,session_status='open' if p.ongoing and b==as_of else 'closed',source='network'))

def dashboard(db,p,date=None,period='This week'):
    as_of=now();tz=ZoneInfo('America/New_York')
    selected=date or as_of.astimezone(tz).date()
    start=datetime.combine(selected,time.min,tz).astimezone(timezone.utc);end=datetime.combine(selected+timedelta(days=1),time.min,tz).astimezone(timezone.utc)
    users=db.scalars(scope(User,p).where(User.role=='doctor')).all()
    me=get_record(db,User,p.id,p)
    locations=db.scalars(scope(Location,p)).all();locs={l.id:l for l in locations}
    departments={d.id:d.name for d in db.scalars(scope(Department,p))}
    sessions=db.scalars(scope(AttendanceSession,p).where(AttendanceSession.started_at<end,(AttendanceSession.ended_at>start)|(AttendanceSession.ended_at.is_(None)))).all()
    report_rows=db.scalars(scope(ActivityReport,p).order_by(ActivityReport.created_at.desc()).limit(500)).all()
    names={u.id:u.full_name for u in users};names[me.id]=me.full_name
    latest={}
    for event in db.scalars(scope(NetworkEvent,p).order_by(NetworkEvent.event_timestamp)):
        latest[event.doctor_id]=event
    docs=[]
    for u in users:
        us=[s for s in sessions if s.doctor_id==u.id and locs[s.location_id].name!='Unknown / Transit']
        # Closed periods use exact duration; open periods never extend past last evidence TTL.
        seconds=sum(clipped_seconds(s.started_at,s.ended_at or s.started_at+timedelta(seconds=s.duration_seconds),start,end) for s in us)
        event=latest.get(u.id)
        current=next((s for s in sessions if s.doctor_id==u.id and s.ended_at is None and s.source=='network' and s.confidence_status in ('network_detected','grace_merged') and (as_of-(s.started_at+timedelta(seconds=s.duration_seconds))).total_seconds()<120),None)
        fresh=current is not None
        loc=locs.get(current.location_id) if fresh else None
        docs.append({'id':u.id,'full_name':u.full_name,'email':u.email,'department':departments.get(u.department_id,'Unassigned'),'location':loc.name if loc else None,'location_id':loc.id if loc else None,'status':'Disabled' if u.status=='disabled' else 'Present' if fresh else 'Last seen' if event else 'Absent','hours':round(seconds/3600,3),'first_arrival':min((s.started_at for s in us),default=None),'last_seen':event.event_timestamp if event else None,'initials':''.join(x[0] for x in u.full_name.removeprefix('Dr. ').split())[:2],'color':['#e5eaf4','#e3efea','#f4e9e2'][len(u.full_name)%3]})
    report_data=[{**json_row(r),'doctor_name':names.get(r.doctor_id,'Doctor')} for r in report_rows]
    corrections=[{**json_row(c),'doctor_name':names.get(c.doctor_id,'Doctor')} for c in db.scalars(scope(Correction,p).order_by(Correction.created_at.desc()))]
    audit_rows=[json_row(a) for a in db.scalars(scope(AuditLog,p).order_by(AuditLog.timestamp.desc()).limit(100))] if p.role=='admin' else []
    monday=selected-timedelta(days=selected.weekday())-(timedelta(days=7) if period=='Last week' else timedelta())
    weekly=[]
    all_sessions=db.scalars(scope(AttendanceSession,p).where(AttendanceSession.started_at>=datetime.combine(monday-timedelta(days=1),time.min,tz))).all()
    for day_num in range(7):
        day=monday+timedelta(days=day_num);a=datetime.combine(day,time.min,tz).astimezone(timezone.utc);b=datetime.combine(day+timedelta(days=1),time.min,tz).astimezone(timezone.utc)
        totals={}
        for s in all_sessions:
            if locs[s.location_id].name=='Unknown / Transit':continue
            # Reconciler maintains duration as evidence-time snapshots; no uncapped open-ended counting.
            session_end=s.ended_at or s.started_at+timedelta(seconds=s.duration_seconds)
            totals[s.location_id]=totals.get(s.location_id,0)+clipped_seconds(s.started_at,session_end,a,b)/3600
        visible=[l for l in locations if l.active]
        weekly.append({'day':day.strftime('%a'),'date':day.isoformat(),'main':round(totals.get(visible[0].id,0),1) if visible else 0,'office':round(totals.get(visible[1].id,0),1) if len(visible)>1 else 0,'clinic':round(sum(totals.get(l.id,0) for l in visible[2:]),1),'own':round(sum(totals.values()),2) if p.role=='doctor' else 0})
    return {'mode':'production','role':p.role,'user':{'id':me.id,'full_name':me.full_name,'email':me.email,'department':departments.get(me.department_id,'Administration')},'doctors':docs,'locations':[{**json_row(l),'ssid':db.scalar(select(WifiNetwork.ssid).where(WifiNetwork.organization_id==p.organization_id,WifiNetwork.location_id==l.id)) or 'Unmapped','count':sum(d['location_id']==l.id for d in docs),'capacity':100,'color':'#188e82'} for l in locations if l.name!='Unknown / Transit'],'reports':report_data,'sessions':[{**json_row(s),'location':locs[s.location_id].name} for s in sessions],'corrections':corrections,'audit':audit_rows,'weekly':weekly,'metrics':{'total':len(docs),'present':sum(d['status']=='Present' for d in docs),'hours':round(sum(d['hours'] for d in docs),1),'reports':len(report_data),'pending':sum(r['review_status']=='pending' for r in report_data),'exceptions':sum(c['approval_status']=='pending' for c in corrections)},'updated_at':as_of,'settings':me.preferences}
