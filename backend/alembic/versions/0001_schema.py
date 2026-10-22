"""Initial normalized schema, tenant RLS, and overlap protection."""
from alembic import op
from pathlib import Path
revision='0001'
down_revision=None

def upgrade():
    for statement in Path(__file__).with_name('0001_tables.sql').read_text().split(';'):
        if statement.strip():op.execute(statement)
    op.execute('CREATE EXTENSION IF NOT EXISTS btree_gist')
    op.execute("ALTER TABLE attendance_sessions ADD CONSTRAINT no_overlapping_attendance EXCLUDE USING gist (organization_id WITH =, doctor_id WITH =, tstzrange(started_at, ended_at, '[)') WITH &&) DEFERRABLE INITIALLY DEFERRED")
    org="organization_id = current_setting('app.organization_id',true)"
    admin="current_setting('app.role',true) IN ('admin','processor')"
    # Restrict both reads and writes; backend also scopes every query explicitly.
    for table in ('departments','users','locations','wifi_networks','registered_devices','network_events','attendance_sessions','activity_reports','audio_recordings','attendance_corrections','audit_logs','processing_jobs'):
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        own="id = current_setting('app.user_id',true)" if table=='users' else "doctor_id = current_setting('app.user_id',true)" if table in ('registered_devices','network_events','attendance_sessions','activity_reports','audio_recordings','attendance_corrections','processing_jobs') else 'true'
        read=f"({org}) AND (({admin}) OR ({own}))"
        if table=='audit_logs':
            op.execute(f'CREATE POLICY audit_read ON audit_logs FOR SELECT USING (({org}) AND ({admin}))')
            op.execute(f"CREATE POLICY audit_insert ON audit_logs FOR INSERT WITH CHECK (({org}) AND (actor_id = current_setting('app.user_id',true) OR ({admin})))")
        else:
            op.execute(f'CREATE POLICY tenant_read ON {table} FOR SELECT USING ({read})')
            # Doctor writes limited to own operational records/profile; network and attendance writes use processor transactions.
            can_write=f"({org}) AND (({admin}) OR ({own}))" if table in ('users','activity_reports','audio_recordings','attendance_corrections','processing_jobs','attendance_sessions') else f'({org}) AND ({admin})'
            if table=='users':can_write=f"({org}) AND (({admin}) OR (({own}) AND role='doctor' AND status='active'))"
            if table=='attendance_corrections':can_write=f"({org}) AND (({admin}) OR (({own}) AND approval_status='pending' AND reviewed_by IS NULL))"
            for operation in ('INSERT','UPDATE','DELETE'):
                clause=f'WITH CHECK ({can_write})' if operation=='INSERT' else f'USING ({can_write})'+(f' WITH CHECK ({can_write})' if operation=='UPDATE' else '')
                op.execute(f'CREATE POLICY tenant_{operation.lower()} ON {table} FOR {operation} {clause}')
    op.execute('ALTER TABLE organizations ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE organizations FORCE ROW LEVEL SECURITY')
    op.execute("CREATE POLICY organization_scope ON organizations USING (id = current_setting('app.organization_id',true))")
    # Tenant consistency is enforced for references even when an accidental query omits scope.
    for table in ('users','departments','locations','wifi_networks','registered_devices','attendance_sessions','activity_reports'):
        op.execute(f'ALTER TABLE {table} ADD CONSTRAINT {table}_tenant_id UNIQUE (organization_id,id)')
    refs={'users':[('department_id','departments')],'wifi_networks':[('location_id','locations')],'registered_devices':[('doctor_id','users')],'network_events':[('doctor_id','users'),('device_id','registered_devices'),('network_id','wifi_networks'),('location_id','locations')],'attendance_sessions':[('doctor_id','users'),('location_id','locations')],'activity_reports':[('doctor_id','users'),('location_id','locations')],'audio_recordings':[('doctor_id','users'),('report_id','activity_reports')],'attendance_corrections':[('doctor_id','users'),('reviewed_by','users')],'audit_logs':[('actor_id','users')],'processing_jobs':[('doctor_id','users')]}
    for table,links in refs.items():
        for col,target in links:op.execute(f'ALTER TABLE {table} ADD CONSTRAINT {table}_{col}_tenant_fk FOREIGN KEY (organization_id,{col}) REFERENCES {target}(organization_id,id)')

def downgrade():
    raise RuntimeError('Destructive downgrade is disabled. Restore from a reviewed backup.')
