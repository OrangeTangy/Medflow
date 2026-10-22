import hashlib, secrets, time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
import httpx, jwt
from fastapi import Request, HTTPException, Depends, APIRouter
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from redis import Redis
from .config import settings
from .db import AuthDB, SessionLocal, tenant_context
from .models import User, AuthSession, Identity

router=APIRouter()
@dataclass
class Principal:
    id:str
    organization_id:str
    role:str

def token_hash(value):return hashlib.sha256(value.encode()).hexdigest()
def aware(value):return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

def principal(request:Request)->Principal:
    token=request.cookies.get('medflow_session')
    if not token:raise HTTPException(401,'Sign in through your hospital identity provider')
    with AuthDB() as db:
        row=db.execute(select(AuthSession,User).join(User,User.id==AuthSession.user_id).where(AuthSession.token_hash==token_hash(token))).first()
        if not row or aware(row[0].expires_at)<=datetime.now(timezone.utc) or row[1].status!='active':raise HTTPException(401,'Your session expired or account is disabled')
        user=row[1]
        return Principal(user.id,user.organization_id,user.role)

def database(p:Principal=Depends(principal)):
    with SessionLocal() as db:
        tenant_context(db,p.organization_id,p.id,p.role)
        yield db
        db.commit()

def administrator(p:Principal=Depends(principal)):
    if p.role!='admin':raise HTTPException(403,'Administrator permission required')
    return p

def guard_mutation(request:Request):
    if request.method in ('POST','PUT','PATCH','DELETE') and not request.url.path.startswith('/api/integrations/'):
        origin=request.headers.get('origin')
        if origin!=settings().public_origin or request.headers.get('sec-fetch-site')=='cross-site':
            raise HTTPException(403,'Invalid request origin')

def rate_limit(key,limit=120,window=60):
    try:
        r=Redis.from_url(settings().redis_url, socket_connect_timeout=2)
        k=f'rate:{key}:{int(time.time())//window}'
        count=r.incr(k)
        if count==1:r.expire(k,window+5)
        if count>limit:raise HTTPException(429,'Too many requests; try again shortly')
    except HTTPException:raise
    except Exception:raise HTTPException(503,'Request protection temporarily unavailable')

async def discovery():
    s=settings()
    if not s.oidc_issuer or len(s.session_secret)<32:raise HTTPException(503,'Hospital identity provider is not configured')
    async with httpx.AsyncClient(timeout=15) as client:
        r=await client.get(s.oidc_issuer.rstrip('/')+'/.well-known/openid-configuration');r.raise_for_status();d=r.json()
        if d.get('issuer')!=s.oidc_issuer:raise HTTPException(503,'OIDC issuer mismatch')
        for key in ('authorization_endpoint','token_endpoint','jwks_uri'):
            if not d[key].startswith('https://'):raise HTTPException(503,'OIDC endpoints require TLS')
        return d

@router.get('/api/auth/login')
async def login():
    s=settings();d=await discovery();state=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48)
    import base64
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    response=RedirectResponse(d['authorization_endpoint']+'?'+urlencode({'client_id':s.oidc_client_id,'redirect_uri':s.public_origin+'/api/auth/callback','response_type':'code','scope':'openid profile email','state':state,'nonce':nonce,'code_challenge':challenge,'code_challenge_method':'S256','acr_values':s.oidc_mfa_claim}))
    ticket=jwt.encode({'state':state,'nonce':nonce,'verifier':verifier,'exp':int(time.time())+600},s.session_secret,algorithm='HS256')
    response.set_cookie('medflow_oidc',ticket,secure=True,httponly=True,samesite='lax',max_age=600,path='/api/auth')
    return response

@router.get('/api/auth/callback')
async def callback(request:Request,code:str,state:str):
    s=settings();d=await discovery()
    try:ticket=jwt.decode(request.cookies.get('medflow_oidc',''),s.session_secret,algorithms=['HS256'])
    except jwt.PyJWTError:raise HTTPException(400,'Invalid or expired sign-in state')
    if not secrets.compare_digest(state,ticket['state']):raise HTTPException(400,'Sign-in state mismatch')
    async with httpx.AsyncClient(timeout=20) as client:
        r=await client.post(d['token_endpoint'],data={'grant_type':'authorization_code','client_id':s.oidc_client_id,'client_secret':s.oidc_client_secret,'code':code,'redirect_uri':s.public_origin+'/api/auth/callback','code_verifier':ticket['verifier']})
        if r.status_code!=200:raise HTTPException(401,'Identity provider rejected sign-in')
        token=r.json().get('id_token','')
        jwks=(await client.get(d['jwks_uri'])).json()
    try:
        header=jwt.get_unverified_header(token)
        key=next(k for k in jwks['keys'] if k['kid']==header.get('kid'))
        claims=jwt.decode(token,jwt.PyJWK.from_dict(key).key,algorithms=['RS256','ES256'],audience=s.oidc_client_id,issuer=s.oidc_issuer,options={'require':['exp','iat','sub','nonce']})
        if claims['nonce']!=ticket['nonce']:raise ValueError('nonce')
        if s.oidc_mfa_claim not in claims.get('amr',[]) and claims.get('acr')!=s.oidc_mfa_claim:raise HTTPException(403,'Multi-factor authentication is required')
    except HTTPException:raise
    except (jwt.PyJWTError,KeyError,StopIteration,ValueError):raise HTTPException(401,'Invalid identity token')
    raw=secrets.token_urlsafe(48)
    # AuthDB uses a separate, narrowly scoped authentication role; no attendance access.
    with AuthDB() as db:
        user=db.scalar(select(User).join(Identity,Identity.user_id==User.id).where(Identity.issuer==s.oidc_issuer,Identity.subject==claims['sub'],User.status=='active'))
        if not user:raise HTTPException(403,'Ask your administrator to provision your enterprise identity')
        db.add(AuthSession(token_hash=token_hash(raw),user_id=user.id,expires_at=datetime.now(timezone.utc)+timedelta(hours=8)));db.commit()
    response=RedirectResponse(s.public_origin+'/',status_code=303)
    response.delete_cookie('medflow_oidc',path='/api/auth')
    response.set_cookie('medflow_session',raw,secure=True,httponly=True,samesite='lax',max_age=8*3600,path='/')
    return response

@router.post('/api/auth/logout',dependencies=[Depends(guard_mutation)])
def logout(request:Request,p:Principal=Depends(principal)):
    with AuthDB() as db:
        row=db.scalar(select(AuthSession).where(AuthSession.token_hash==token_hash(request.cookies['medflow_session'])))
        if row:db.delete(row);db.commit()
    response=RedirectResponse(settings().public_origin+'/',status_code=303);response.delete_cookie('medflow_session');return response
