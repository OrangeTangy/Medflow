"""Promote immutable images through a migration task and ECS rolling deployment.
Existing ECS service/task definitions own infrastructure, secrets, networking,
and execution roles. This script preserves those reviewed settings.
"""
import os,copy,boto3
ecs=boto3.client('ecs')
cluster=os.environ['ECS_CLUSTER'];release=os.environ['RELEASE_SHA'];registry=os.environ['REGISTRY']
if len(release)!=40 or any(c not in '0123456789abcdef' for c in release):raise SystemExit('Use a complete reviewed 40-character commit SHA')
services=[os.environ['ECS_WEB_SERVICE'],os.environ['ECS_WORKER_SERVICE'],os.environ['ECS_SCHEDULER_SERVICE']]
original={}
allowed={'family','taskRoleArn','executionRoleArn','networkMode','containerDefinitions','volumes','placementConstraints','requiresCompatibilities','cpu','memory','pidMode','ipcMode','proxyConfiguration','inferenceAccelerators','ephemeralStorage','runtimePlatform'}
def clean(task):return {k:copy.deepcopy(v) for k,v in task.items() if k in allowed}
def task_for(service):
    data=ecs.describe_services(cluster=cluster,services=[service])['services'][0];original[service]=data['taskDefinition'];task=clean(ecs.describe_task_definition(taskDefinition=data['taskDefinition'])['taskDefinition'])
    for c in task['containerDefinitions']:c['image']=registry+('/medflow-web:' if c['name']=='web' else '/medflow-api:')+release
    return data,task
service_data,api_task=task_for(services[0]);migration=clean(api_task);migration['family']=api_task['family']+'-migration';migration['containerDefinitions']=[c for c in migration['containerDefinitions'] if c['name']=='api']
if len(migration['containerDefinitions'])!=1:raise SystemExit('Web service must include a container named api')
container=migration['containerDefinitions'][0];container['command']=['alembic','upgrade','head'];container.pop('healthCheck',None);container.pop('dependsOn',None)
container['secrets']=[s for s in container.get('secrets',[]) if s['name']!='DATABASE_URL']+[{'name':'DATABASE_URL','valueFrom':os.environ['MIGRATION_DATABASE_SECRET_ARN']}]
migration_arn=ecs.register_task_definition(**migration)['taskDefinition']['taskDefinitionArn']
run=ecs.run_task(cluster=cluster,taskDefinition=migration_arn,launchType='FARGATE',networkConfiguration=service_data['networkConfiguration'])
if run.get('failures'):raise SystemExit('Migration task could not start')
task_id=run['tasks'][0]['taskArn'];ecs.get_waiter('tasks_stopped').wait(cluster=cluster,tasks=[task_id],WaiterConfig={'Delay':10,'MaxAttempts':90})
stopped=ecs.describe_tasks(cluster=cluster,tasks=[task_id])['tasks'][0]
if any(c.get('exitCode')!=0 for c in stopped['containers']):raise SystemExit('Database migration failed. No services were promoted.')
try:
    for service in services:
        if service==services[0]:task=api_task
        else:_,task=task_for(service)
        arn=ecs.register_task_definition(**task)['taskDefinition']['taskDefinitionArn'];ecs.update_service(cluster=cluster,service=service,taskDefinition=arn)
    ecs.get_waiter('services_stable').wait(cluster=cluster,services=services,WaiterConfig={'Delay':15,'MaxAttempts':80})
except Exception:
    for service,arn in original.items():ecs.update_service(cluster=cluster,service=service,taskDefinition=arn)
    raise
print('Migration completed and all services stabilized at release',release)
