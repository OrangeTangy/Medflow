"""Development-only signed RADIUS relay simulator; uses already enrolled identities.
Run with INTEGRATION_SECRET in the environment, never as a command-line value.
All generated events carry provider IDs prefixed simulator and are traceable.
"""
import argparse,os,uuid,json,time,hmac,hashlib
from datetime import datetime,timezone,timedelta
import urllib.request
parser=argparse.ArgumentParser();parser.add_argument('--endpoint',required=True);parser.add_argument('--identity',required=True);parser.add_argument('--device',required=True);parser.add_argument('--controller',required=True);parser.add_argument('--minutes',type=int,default=60);args=parser.parse_args()
if not 1<=args.minutes<=1440:raise SystemExit('Duration must be between 1 minute and 24 hours')
secret=os.environ.get('INTEGRATION_SECRET','')
if len(secret)<32:raise SystemExit('Set the development integration signing secret in the environment')
session='simulator-'+str(uuid.uuid4());start=datetime.now(timezone.utc)-timedelta(minutes=args.minutes)
moments=[(0,'Start')]+[(n,'Interim-Update') for n in range(5,args.minutes,5)]+[(args.minutes,'Stop')]
for minute,event_type in moments:
    body=json.dumps({'Event-Id':f'{session}:{minute}:{event_type}','EAP-Identity':args.identity,'Device-Certificate-Id':args.device,'NAS-Identifier':args.controller,'Acct-Session-Id':session,'Acct-Status-Type':event_type,'Event-Timestamp':(start+timedelta(minutes=minute)).isoformat()},separators=(',',':')).encode()
    stamp=str(int(time.time()));signature=hmac.new(secret.encode(),stamp.encode()+b'.'+body,hashlib.sha256).hexdigest()
    request=urllib.request.Request(args.endpoint.rstrip('/')+'/api/integrations/radius/events',data=body,headers={'Content-Type':'application/json','X-Medflow-Timestamp':stamp,'X-Medflow-Signature':signature})
    with urllib.request.urlopen(request,timeout=15) as response:
        if response.status!=202:raise SystemExit('Event was not accepted')
print(f'Accepted {len(moments)} simulated accounting events. Inspect processing jobs and attendance before using a live relay.')
