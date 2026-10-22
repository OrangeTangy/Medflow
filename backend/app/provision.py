"""One-time, audited operator provisioning, run with migration-owner credentials."""
import argparse
from sqlalchemy import select
from .db import SessionLocal
from .models import Organization,User,Identity,Department,AuditLog
from .config import settings

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--organization',required=True);parser.add_argument('--name',required=True);parser.add_argument('--email',required=True);parser.add_argument('--subject',required=True);args=parser.parse_args()
    if not settings().oidc_issuer:raise SystemExit('Configure OIDC_ISSUER first')
    with SessionLocal() as db:
        org=db.scalar(select(Organization).where(Organization.name==args.organization))
        if not org:org=Organization(name=args.organization,settings={'doctor_exports_enabled':False,'audio_retention_days':0});db.add(org);db.flush()
        if db.scalar(select(Identity).where(Identity.issuer==settings().oidc_issuer,Identity.subject==args.subject)):raise SystemExit('Identity already provisioned')
        user=User(organization_id=org.id,full_name=args.name,email=args.email.lower(),role='admin');db.add(user);db.flush();db.add(Identity(issuer=settings().oidc_issuer,subject=args.subject,user_id=user.id));db.add(AuditLog(organization_id=org.id,actor_id=user.id,action='operator:provision_admin',resource_type='user',resource_id=user.id));db.commit();print('Administrator provisioned. Organization ID:',org.id)
if __name__=='__main__':main()
