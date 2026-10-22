"""Durable SQL outbox + Celery scheduler. Committed jobs survive Redis outages."""
import json
from datetime import timedelta
import boto3,httpx
from celery import Celery
from sqlalchemy import create_engine,select,delete
from sqlalchemy.orm import sessionmaker
from redis import Redis
from .config import settings
from .models import ProcessingJob,AudioRecording,Organization,User,now
from .db import tenant_context
from .services import rebuild

s=settings()
celery=Celery('medflow',broker=s.redis_url)
celery.conf.update(task_acks_late=True,worker_prefetch_multiplier=1,task_reject_on_worker_lost=True,broker_connection_retry_on_startup=True,beat_schedule={'dispatch':{'task':'app.worker.dispatch','schedule':5.0},'reconcile-stale':{'task':'app.worker.sweep','schedule':60.0},'retention':{'task':'app.worker.retention','schedule':3600.0}})
WorkerDB=sessionmaker(create_engine(s.worker_database_url or s.database_url,pool_pre_ping=True),expire_on_commit=False)

@celery.task(name='app.worker.dispatch')
def dispatch():
    # SKIP LOCKED plus a database transaction prevents concurrent job duplication.
    for _ in range(100):
        with WorkerDB() as db:
            job=db.scalar(select(ProcessingJob).where(ProcessingJob.status.in_(['queued','retry']),ProcessingJob.attempts<5).order_by(ProcessingJob.created_at).with_for_update(skip_locked=True).limit(1))
            if not job:break
            job.attempts+=1;job.status='processing';org=job.organization_id;doctor=job.doctor_id;cleanup_recording=None
            try:
                with db.begin_nested():
                    tenant_context(db,org,'','processor')
                    if job.kind=='reconcile':rebuild(db,org,doctor)
                    elif job.kind=='transcription':
                        if not s.transcription_approved:raise RuntimeError('Provider approval missing')
                        recording=db.get(AudioRecording,job.payload['recording_id'])
                        if not recording:raise RuntimeError('Recording not found')
                        audio=boto3.client('s3').get_object(Bucket=s.audio_bucket,Key=recording.storage_reference)['Body'].read()
                        with httpx.Client(timeout=180) as client:
                            response=client.post(s.transcription_endpoint,headers={'Authorization':'Bearer '+s.transcription_api_key},files={'audio':('recording',audio,job.payload['content_type'])});response.raise_for_status()
                            transcript=response.json()['text']
                        if not isinstance(transcript,str) or len(transcript)>100000:raise RuntimeError('Invalid provider response')
                        job.result={'transcript':transcript}
                        if s.audio_retention_days==0:cleanup_recording=(recording.id,recording.storage_reference)
                    job.status='completed';job.error=None
            except Exception:
                job.status='failed' if job.attempts>=5 else 'retry'
                job.error='Processing failed. Contact your administrator with the job ID.'
            db.commit()
        # Commit the transcript before deleting its only source recording.
        # If cleanup fails, retention maintenance retries the remaining row.
        if cleanup_recording and job.status=='completed':
            try:
                boto3.client('s3').delete_object(Bucket=s.audio_bucket,Key=cleanup_recording[1])
                with WorkerDB() as cleanup_db:
                    cleanup_db.execute(delete(AudioRecording).where(AudioRecording.id==cleanup_recording[0]));cleanup_db.commit()
            except Exception:pass
        try:
            redis=Redis.from_url(s.redis_url)
            message=json.dumps({'type':'presence_updated' if job.kind=='reconcile' else 'transcription_updated','job_id':job.id})
            redis.publish(f'presence:{org}:admin',message);redis.publish(f'presence:{org}:{doctor}',message)
        except Exception:pass # Durable state is committed; clients also poll.

@celery.task(name='app.worker.sweep')
def sweep():
    with WorkerDB() as db:
        for org in db.scalars(select(Organization)):
            tenant_context(db,org.id,'','processor')
            for doctor in db.scalars(select(User).where(User.organization_id==org.id,User.role=='doctor',User.status=='active')):rebuild(db,org.id,doctor.id)
        db.commit()

@celery.task(name='app.worker.retention')
def retention():
    with WorkerDB() as db:
        for recording in db.scalars(select(AudioRecording).where(AudioRecording.retention_expiration<now())):
            boto3.client('s3').delete_object(Bucket=s.audio_bucket,Key=recording.storage_reference);db.delete(recording)
        # Workforce data deletion is organization-policy-controlled, never inferred.
        for org in db.scalars(select(Organization)):
            days=org.settings.get('transcription_job_retention_days',30)
            db.execute(delete(ProcessingJob).where(ProcessingJob.organization_id==org.id,ProcessingJob.kind=='transcription',ProcessingJob.created_at<now()-timedelta(days=days),ProcessingJob.status.in_(['completed','failed'])))
        db.commit()
