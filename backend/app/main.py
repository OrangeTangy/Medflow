import asyncio, hashlib, hmac, json, time, uuid
from datetime import date,datetime,timezone,timedelta
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from fastapi import FastAPI,Depends,HTTPException,Request,UploadFile,File,Query
from fastapi.responses import JSONResponse,Response,StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select,delete,text
from sqlalchemy.exc import IntegrityError
from redis import Redis
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from .config import settings
from .models import *
from .security import router,principal,administrator,database,Principal,guard_mutation,rate_limit
from .services import scope,get_record,json_row,dashboard,audit,lock_doctor,rebuild
from .schemas import *
from .adapters import ADAPTERS
from .exports import csv_export,pdf_export

app=FastAPI(title='Medflow Hospital Presence API',version='1.0.0',dependencies=[Depends(guard_mutation)])
app.include_router(router)
app.add_middleware(CORSMiddleware,allow_origins=[settings().public_origin],allow_credentials=True,allow_methods=['GET','POST','PATCH','DELETE'],allow_headers=['Content-Type'])
requests=Counter('medflow_http_requests_total','HTTP responses',['method','status'])

@app.middleware('http')
async def headers(request:Request,call_next):
    request_id=str(uuid.uuid4())
    if request.url.path.startswith('/api/') and not request.url.path.startswith('/api/integrations/'):
        try:rate_limit(hashlib.sha256((request.cookies.get('medflow_session') or (request.client.host if request.client else 'unknown')).encode()).hexdigest())
        except HTTPException as exc:return JSONResponse({'detail':exc.detail},status_code=exc.status_code)
    response=await call_next(request)
    for key,value in {'X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin','Cache-Control':'no-store','X-Request-ID':request_id,'Permissions-Policy':'camera=(), geolocation=()','Strict-Transport-Security':'max-age=31536000; includeSubDomains'}.items():response.headers[key]=value
    requests.labels(request.method,str(response.status_code)).inc()
    return response

@app.exception_handler(IntegrityError)
async def integrity(request,exc):return JSONResponse({'detail':'The operation conflicts with an existing record or overlapping attendance period'},409)

@app.get('/health/live')
def live():return {'status':'ok'}
@app.get('/health/ready')
def ready():
    from .db import SessionLocal
    try:
        with SessionLocal() as db:db.execute(text('SELECT 1'))
        Redis.from_url(settings().redis_url,socket_connect_timeout=2).ping()
        return {'status':'ready'}
    except Exception:raise HTTPException(503,'Dependency unavailable')
@app.get('/metrics',include_in_schema=False)
def metrics(p=Depends(administrator)):return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)

@app.get('/api/me')
def me(p=Depends(principal),db=Depends(database)):
    u=get_record(db,User,p.id,p);audit(db,p,'read','profile',u.id);return json_row(u)
@app.get('/api/dashboard')
def get_dashboard(date:date|None=None,period:str='This week',p=Depends(principal),db=Depends(database)):
    result=dashboard(db,p,date,period);audit(db,p,'read','dashboard');return result
@app.get('/api/users')
def users(p=Depends(administrator),db=Depends(database)):
    audit(db,p,'read','users');return [json_row(u) for u in db.scalars(scope(User,p))]
@app.get('/api/users/{user_id}')
def user_profile(user_id:str,p=Depends(principal),db=Depends(database)):
    u=get_record(db,User,user_id,p);audit(db,p,'read','profile',u.id);return json_row(u)
@app.post('/api/users',status_code=201)
def create_user(body:UserInput,p=Depends(administrator),db=Depends(database)):
    dep=db.scalar(scope(Department,p).where(Department.name==body.department))
    if not dep:dep=Department(organization_id=p.organization_id,name=body.department);db.add(dep);db.flush()
    u=User(organization_id=p.organization_id,full_name=body.full_name,email=body.email.lower(),department_id=dep.id,role='doctor');db.add(u);db.flush()
    db.add(Identity(issuer=settings().oidc_issuer,subject=body.identity_reference,user_id=u.id));audit(db,p,'create','user',u.id);return json_row(u)
class UserPatch(Strict):status:Literal['active','disabled']
@app.patch('/api/users/{user_id}')
def update_user(user_id:str,body:UserPatch,p=Depends(administrator),db=Depends(database)):
    u=get_record(db,User,user_id,p)
    if u.id==p.id:raise HTTPException(409,'You cannot disable your own administrative account')
    u.status=body.status;audit(db,p,'update','user',u.id);return {'status':'updated'}
@app.patch('/api/profile')
def profile(body:ProfileInput,p=Depends(principal),db=Depends(database)):
    u=get_record(db,User,p.id,p);u.full_name=body.full_name;u.preferences={'notifications':body.notifications};audit(db,p,'update','profile',u.id);return {'status':'saved'}

@app.get('/api/attendance')
def attendance(doctor_id:str|None=None,p=Depends(principal),db=Depends(database)):
    if doctor_id and p.role!='admin' and doctor_id!=p.id:raise HTTPException(403,'Only your own attendance is accessible')
    q=scope(AttendanceSession,p)
    if doctor_id:q=q.where(AttendanceSession.doctor_id==doctor_id)
    audit(db,p,'read','attendance');return [json_row(s) for s in db.scalars(q.order_by(AttendanceSession.started_at.desc()).limit(1000))]
@app.get('/api/presence')
def presence(p=Depends(principal),db=Depends(database)):
    d=dashboard(db,p);return {'doctors':d['doctors'],'observed_at':d['updated_at'],'stale_after_seconds':settings().presence_stale_seconds}
@app.get('/api/analytics')
def analytics(date:date|None=None,p=Depends(principal),db=Depends(database)):
    d=dashboard(db,p,date);audit(db,p,'read','analytics');return {'weekly':d['weekly'],'metrics':d['metrics']}
@app.get('/api/reports')
def reports(p=Depends(principal),db=Depends(database)):
    audit(db,p,'read','activity_reports');return [json_row(r) for r in db.scalars(scope(ActivityReport,p).order_by(ActivityReport.created_at.desc()).limit(500))]
@app.get('/api/reports/{rid}')
def get_report(rid:str,p=Depends(principal),db=Depends(database)):
    r=get_record(db,ActivityReport,rid,p);audit(db,p,'read','activity_report',r.id);return json_row(r)
@app.post('/api/reports',status_code=201)
def report(body:ReportInput,p=Depends(principal),db=Depends(database)):
    if p.role!='doctor':raise HTTPException(403,'Doctor account required to author an activity report')
    if body.location_id:get_record(db,Location,body.location_id,p)
    r=ActivityReport(organization_id=p.organization_id,doctor_id=p.id,**body.model_dump());db.add(r);db.flush();audit(db,p,'create','activity_report',r.id);return json_row(r)
@app.patch('/api/reports/{rid}')
def edit_report(rid:str,body:ReportInput,p=Depends(principal),db=Depends(database)):
    r=get_record(db,ActivityReport,rid,p)
    if r.doctor_id!=p.id:raise HTTPException(403,'Only the author may edit this transcript')
    if body.location_id:get_record(db,Location,body.location_id,p)
    # Original transcript is immutable. Every edit invalidates prior review.
    r.edited_transcript=body.edited_transcript;r.category=body.category;r.tags=body.tags;r.location_id=body.location_id;r.review_status='pending';r.summary={};audit(db,p,'update','activity_report',r.id);return json_row(r)
@app.post('/api/reports/{rid}/review')
def review_report(rid:str,p=Depends(administrator),db=Depends(database)):
    r=get_record(db,ActivityReport,rid,p);r.review_status='reviewed';audit(db,p,'review','activity_report',rid);return {'status':'reviewed'}

@app.post('/api/reports/{rid}/summary')
async def summarize_report(rid:str,p=Depends(principal),db=Depends(database)):
    import httpx
    r=get_record(db,ActivityReport,rid,p);s=settings()
    if r.doctor_id!=p.id:raise HTTPException(403,'Only the author may request an activity summary')
    if not s.summary_approved or not s.summary_endpoint.startswith('https://'):raise HTTPException(503,'An approved AI summary provider is not configured')
    async with httpx.AsyncClient(timeout=60) as client:
        response=await client.post(s.summary_endpoint,headers={'Authorization':'Bearer '+s.summary_api_key},json={'transcript':r.edited_transcript,'instruction':'Return categories with exact source character offsets. Do not infer or invent activities.','response_schema':{'items':[{'category':'Other','start':0,'end':10}]}})
        if response.status_code!=200:raise HTTPException(502,'Summary provider could not complete the request')
    items=response.json().get('items',[])
    if not isinstance(items,list) or len(items)>100:raise HTTPException(502,'Invalid summary response')
    validated=[]
    for item in items:
        a,b=item.get('start'),item.get('end');category=item.get('category')
        if not isinstance(a,int) or not isinstance(b,int) or not 0<=a<b<=len(r.edited_transcript) or category not in ReportInput.model_fields['category'].annotation.__args__:raise HTTPException(502,'Summary is not traceable to the source transcript')
        validated.append({'category':category,'start':a,'end':b,'text':r.edited_transcript[a:b]})
    r.summary={'ai_generated':True,'source_sha256':hashlib.sha256(r.edited_transcript.encode()).hexdigest(),'items':validated,'generated_at':now().isoformat(),'reviewed':False}
    audit(db,p,'generate_summary','activity_report',rid);return r.summary

class SummaryEdit(Strict):
    items:list[dict]=Field(max_length=100)
@app.patch('/api/reports/{rid}/summary')
def edit_summary(rid:str,body:SummaryEdit,p=Depends(principal),db=Depends(database)):
    r=get_record(db,ActivityReport,rid,p)
    if r.doctor_id!=p.id:raise HTTPException(403,'Only the author may review an AI summary')
    if not r.summary:raise HTTPException(409,'Generate a summary first')
    for item in body.items:
        if not isinstance(item.get('text'),str) or len(item['text'])>5000:raise HTTPException(422,'Invalid edited summary')
    r.summary={**r.summary,'doctor_edited_items':body.items,'reviewed':True};audit(db,p,'review_summary','activity_report',rid);return r.summary
@app.post('/api/corrections',status_code=201)
def correction(body:CorrectionInput,p=Depends(principal),db=Depends(database)):
    if p.role!='doctor':raise HTTPException(403,'Doctor account required')
    if body.session_id:get_record(db,AttendanceSession,body.session_id,p)
    get_record(db,Location,body.requested_changes.location_id,p)
    c=Correction(organization_id=p.organization_id,doctor_id=p.id,session_id=body.session_id,reason=body.reason,requested_changes=body.requested_changes.model_dump(mode='json'));db.add(c);db.flush();audit(db,p,'create','attendance_correction',c.id);return json_row(c)
@app.post('/api/corrections/{cid}/review')
def review_correction(cid:str,body:Decision,p=Depends(administrator),db=Depends(database)):
    c=get_record(db,Correction,cid,p);lock_doctor(db,c.doctor_id);db.refresh(c)
    if c.approval_status!='pending':raise HTTPException(409,'This correction has already been reviewed')
    change=Changes.model_validate(c.requested_changes);get_record(db,Location,change.location_id,p)
    if body.decision=='approved':
        db.execute(delete(AttendanceSession).where(AttendanceSession.organization_id==p.organization_id,AttendanceSession.doctor_id==c.doctor_id,AttendanceSession.id==c.session_id))
        overlap=db.scalar(scope(AttendanceSession,p).where(AttendanceSession.doctor_id==c.doctor_id,AttendanceSession.source!='network',AttendanceSession.started_at<change.ended_at,(AttendanceSession.ended_at>change.started_at)|(AttendanceSession.ended_at.is_(None))))
        if overlap:raise HTTPException(409,'Correction overlaps an existing manual or corrected period')
        # Rebuild removes network portions covered by an approved correction.
        db.execute(delete(AttendanceSession).where(AttendanceSession.organization_id==p.organization_id,AttendanceSession.doctor_id==c.doctor_id,AttendanceSession.source=='network'))
        new=AttendanceSession(organization_id=p.organization_id,doctor_id=c.doctor_id,location_id=change.location_id,started_at=change.started_at,ended_at=change.ended_at,duration_seconds=int((change.ended_at-change.started_at).total_seconds()),confidence_status='manually_corrected',session_status='closed',source='correction');db.add(new);db.flush();c.session_id=new.id;rebuild(db,p.organization_id,c.doctor_id)
    c.approval_status=body.decision;c.reviewed_by=p.id;c.reviewed_at=now();audit(db,p,'review:'+body.decision,'attendance_correction',cid);return {'status':body.decision}
@app.post('/api/checkin')
def checkin(body:CheckinInput,p=Depends(principal),db=Depends(database)):
    if p.role!='doctor':raise HTTPException(403,'Doctor account required')
    get_record(db,Location,body.location_id,p);lock_doctor(db,p.id)
    open_session=db.scalar(scope(AttendanceSession,p).where(AttendanceSession.source=='manual',AttendanceSession.ended_at.is_(None)))
    if body.action=='start':
        if open_session:raise HTTPException(409,'You already have an open manual check-in')
        # Expired network data is reconciled around the manual override.
        db.execute(delete(AttendanceSession).where(AttendanceSession.organization_id==p.organization_id,AttendanceSession.doctor_id==p.id,AttendanceSession.source=='network'))
        db.add(AttendanceSession(organization_id=p.organization_id,doctor_id=p.id,location_id=body.location_id,started_at=now(),confidence_status='unverified',source='manual'))
    elif open_session:
        open_session.ended_at=now();open_session.duration_seconds=int((open_session.ended_at-open_session.started_at).total_seconds());open_session.session_status='closed'
    else:raise HTTPException(409,'No open manual check-in exists')
    db.flush();rebuild(db,p.organization_id,p.id);audit(db,p,'manual:'+body.action,'attendance',details={'reason':body.reason});return {'status':'saved','confidence':'unverified'}

@app.get('/api/locations')
def locations(p=Depends(principal),db=Depends(database)):return [json_row(l) for l in db.scalars(scope(Location,p))]
@app.post('/api/locations',status_code=201)
def location(body:LocationInput,p=Depends(administrator),db=Depends(database)):
    l=Location(organization_id=p.organization_id,name=body.name,building=body.building,timezone=body.timezone);db.add(l);db.flush();db.add(WifiNetwork(organization_id=p.organization_id,location_id=l.id,ssid=body.ssid,controller_identifier='unconfigured:'+l.id,authentication_configuration={'status':'pending_enrollment'}));audit(db,p,'create','location',l.id);return json_row(l)
class LocationPatch(Strict):
    name:str=Field(min_length=2,max_length=100)
    ssid:str=Field(min_length=1,max_length=100)
    timezone:str
    active:bool=True
@app.patch('/api/locations/{lid}')
def edit_location(lid:str,body:LocationPatch,p=Depends(administrator),db=Depends(database)):
    l=get_record(db,Location,lid,p)
    try:ZoneInfo(body.timezone)
    except ZoneInfoNotFoundError:raise HTTPException(422,'Unknown facility timezone')
    l.name=body.name;l.timezone=body.timezone;l.active=body.active
    network=db.scalar(scope(WifiNetwork,p).where(WifiNetwork.location_id==lid))
    if network:network.ssid=body.ssid;network.active=body.active
    audit(db,p,'update','location',lid);return json_row(l)
class Enrollment(Strict):
    doctor_id:str
    device_identifier:str=Field(min_length=1,max_length=150)
    identity_reference:str=Field(min_length=1,max_length=250)
@app.post('/api/devices')
def enroll(body:Enrollment,p=Depends(administrator),db=Depends(database)):
    doctor=get_record(db,User,body.doctor_id,p)
    if doctor.role!='doctor':raise HTTPException(422,'Only doctor devices are supported')
    d=Device(organization_id=p.organization_id,**body.model_dump());db.add(d);db.flush();audit(db,p,'enroll','device',d.id);return json_row(d)
class NetworkPatch(Strict):
    controller_identifier:str=Field(min_length=1,max_length=150)
    authentication_configuration:dict
@app.patch('/api/networks/{nid}')
def configure_network(nid:str,body:NetworkPatch,p=Depends(administrator),db=Depends(database)):
    n=get_record(db,WifiNetwork,nid,p);n.controller_identifier=body.controller_identifier;n.authentication_configuration=body.authentication_configuration;audit(db,p,'configure','network',nid);return json_row(n)
@app.get('/api/integration-health')
def integration_health(p=Depends(administrator),db=Depends(database)):
    latest=db.scalar(scope(NetworkEvent,p).order_by(NetworkEvent.received_timestamp.desc()))
    failures=db.scalars(scope(ProcessingJob,p).where(ProcessingJob.status=='failed').limit(100)).all()
    return {'last_received':latest.received_timestamp if latest else None,'failed_jobs':len(failures),'adapters':list(ADAPTERS),'configured':bool(settings().integration_secret)}

@app.post('/api/integrations/{provider}/events',status_code=202)
async def ingest(provider:str,request:Request):
    s=settings()
    if provider not in ADAPTERS:raise HTTPException(404,'Provider adapter unavailable')
    if len(s.integration_secret)<32 or not s.integration_organization_id:raise HTTPException(503,'Network integration not configured')
    raw=await request.body()
    if len(raw)>65536:raise HTTPException(413,'Event too large')
    stamp=request.headers.get('x-medflow-timestamp','');signature=request.headers.get('x-medflow-signature','')
    try:valid=abs(time.time()-int(stamp))<=300
    except ValueError:valid=False
    expected=hmac.new(s.integration_secret.encode(),stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
    if not valid or not hmac.compare_digest(signature,expected):raise HTTPException(401,'Invalid network event signature')
    rate_limit('ingestion:'+s.integration_organization_id,10000)
    try:e=ADAPTERS[provider].normalize(json.loads(raw))
    except Exception:raise HTTPException(422,'Malformed network accounting event')
    if e.event_timestamp>now()+timedelta(minutes=5) or e.event_timestamp<now()-timedelta(days=s.event_max_age_days):raise HTTPException(422,'Event time outside accepted window')
    from .db import SessionLocal,tenant_context
    with SessionLocal() as db:
        tenant_context(db,s.integration_organization_id,'','processor')
        d=db.scalar(select(Device).where(Device.organization_id==s.integration_organization_id,Device.identity_reference==e.identity_reference,Device.device_identifier==e.device_identifier,Device.enrollment_status=='enrolled'))
        n=db.scalar(select(WifiNetwork).where(WifiNetwork.organization_id==s.integration_organization_id,WifiNetwork.controller_identifier==e.controller_identifier,WifiNetwork.active.is_(True)))
        if not d or not n:raise HTTPException(422,'Unknown enrolled identity or network controller')
        u=db.scalar(select(User).where(User.id==d.doctor_id,User.organization_id==s.integration_organization_id,User.status=='active'))
        if not u:raise HTTPException(422,'Doctor account is not active')
        existing=db.scalar(select(NetworkEvent).where(NetworkEvent.organization_id==s.integration_organization_id,NetworkEvent.provider==provider,NetworkEvent.source_event_id==e.source_event_id))
        if existing:return {'id':existing.id,'duplicate':True}
        event=NetworkEvent(organization_id=s.integration_organization_id,doctor_id=d.doctor_id,device_id=d.id,network_id=n.id,location_id=n.location_id,event_type=e.event_type,source_event_id=e.source_event_id,accounting_session_id=e.accounting_session_id,event_timestamp=e.event_timestamp,provider=provider,raw_metadata_reference={'sha256':hashlib.sha256(raw).hexdigest()});db.add(event);db.flush()
        db.add(ProcessingJob(organization_id=s.integration_organization_id,doctor_id=d.doctor_id,kind='reconcile',payload={'event_id':event.id}));d.last_seen=max(d.last_seen or e.event_timestamp,e.event_timestamp)
        try:db.commit()
        except IntegrityError:
            db.rollback();return {'duplicate':True}
        return {'id':event.id,'status':'queued'}

@app.post('/api/transcriptions',status_code=202)
async def upload(audio:UploadFile=File(...),p=Depends(principal),db=Depends(database)):
    s=settings()
    if p.role!='doctor':raise HTTPException(403,'Doctor account required')
    if not s.transcription_approved or not s.transcription_endpoint or not s.audio_bucket or not s.audio_kms_key:raise HTTPException(503,'An approved transcription provider and encrypted private storage must be configured. Use manual text entry.')
    if not s.transcription_endpoint.startswith('https://'):raise HTTPException(503,'Transcription provider must use TLS')
    if audio.content_type not in ('audio/webm','audio/mp4','audio/ogg','audio/wav','audio/mpeg'):raise HTTPException(415,'Unsupported audio type')
    payload=await audio.read(s.max_upload_bytes+1)
    if len(payload)>s.max_upload_bytes:raise HTTPException(413,'Recording exceeds 25 MB limit; split into shorter recordings')
    if not payload:raise HTTPException(422,'Empty recording')
    import boto3
    key=f'{p.organization_id}/{p.id}/{uid()}'
    boto3.client('s3').put_object(Bucket=s.audio_bucket,Key=key,Body=payload,ContentType=audio.content_type,ServerSideEncryption='aws:kms',SSEKMSKeyId=s.audio_kms_key)
    recording=AudioRecording(organization_id=p.organization_id,doctor_id=p.id,storage_reference=key,retention_expiration=now()+timedelta(days=max(s.audio_retention_days,1)));db.add(recording);db.flush()
    job=ProcessingJob(organization_id=p.organization_id,doctor_id=p.id,kind='transcription',payload={'recording_id':recording.id,'content_type':audio.content_type});db.add(job);db.flush();audit(db,p,'upload','audio',recording.id);return {'id':job.id,'status':'queued'}
@app.get('/api/transcriptions/{jid}')
def transcription(jid:str,p=Depends(principal),db=Depends(database)):
    j=get_record(db,ProcessingJob,jid,p);audit(db,p,'read','transcription',jid);return {'id':j.id,'status':j.status,'transcript':j.result.get('transcript'),'error':j.error}
@app.get('/api/audio/{rid}')
def audio_download(rid:str,p=Depends(principal),db=Depends(database)):
    r=get_record(db,AudioRecording,rid,p)
    if r.retention_expiration<=now():raise HTTPException(410,'Recording retention expired')
    import boto3
    obj=boto3.client('s3').get_object(Bucket=settings().audio_bucket,Key=r.storage_reference)
    audit(db,p,'download','audio',rid)
    return StreamingResponse(obj['Body'].iter_chunks(),media_type=obj.get('ContentType','application/octet-stream'))
@app.get('/api/export')
def export(date:date|None=None,format:Literal['csv','pdf']='csv',department:str='All departments',facility:str='All locations',p=Depends(principal),db=Depends(database)):
    me=get_record(db,User,p.id,p)
    org=db.scalar(select(Organization).where(Organization.id==p.organization_id))
    if p.role=='doctor' and not org.settings.get('doctor_exports_enabled',False):raise HTTPException(403,'Your organization has not enabled personal exports')
    rows=dashboard(db,p,date)['doctors'];rows=[d for d in rows if (department=='All departments' or d['department']==department) and (facility=='All locations' or d['location']==facility)]
    audit(db,p,'export:'+format,'attendance',details={'count':len(rows),'date':str(date)})
    return Response(csv_export(rows) if format=='csv' else pdf_export(rows,date or now().date()),media_type='text/csv' if format=='csv' else 'application/pdf',headers={'Content-Disposition':f'attachment; filename="medflow-attendance.{format}"'})
@app.get('/api/audit')
def audit_log(p=Depends(administrator),db=Depends(database)):
    audit(db,p,'read','audit_logs');return [json_row(a) for a in db.scalars(scope(AuditLog,p).order_by(AuditLog.timestamp.desc()).limit(500))]
@app.get('/api/events')
async def events(p=Depends(principal)):
    from redis.asyncio import Redis as AsyncRedis
    async def stream():
        r=AsyncRedis.from_url(settings().redis_url);pub=r.pubsub()
        channel=f'presence:{p.organization_id}:'+('admin' if p.role=='admin' else p.id)
        await pub.subscribe(channel)
        try:
            deadline=time.time()+300
            while time.time()<deadline:
                message=await pub.get_message(ignore_subscribe_messages=True,timeout=10)
                yield 'data: '+(message['data'].decode() if message else '{"type":"heartbeat"}')+'\n\n'
        finally:await pub.aclose();await r.aclose()
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})
