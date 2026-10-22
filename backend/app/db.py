from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from .config import settings

engine=create_engine(settings().database_url, pool_pre_ping=True)
SessionLocal=sessionmaker(engine, expire_on_commit=False)
auth_engine=create_engine(settings().auth_database_url or settings().database_url, pool_pre_ping=True)
AuthDB=sessionmaker(auth_engine, expire_on_commit=False)

def tenant_context(db, organization_id, user_id='', role='doctor'):
    if db.bind.dialect.name=='postgresql':
        for key,value in [('organization_id',organization_id),('user_id',user_id),('role',role)]:
            db.execute(text('SELECT set_config(:key,:value,true)'),{'key':'app.'+key,'value':value})
