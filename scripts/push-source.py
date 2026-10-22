"""Fallback for environments without the installed Sites source helper.
Credential is read through hidden stdin, held only in memory, and passed to Git
through process environment configuration. It is never stored in Git config.
"""
import json,os,sys,subprocess,termios
attrs=termios.tcgetattr(sys.stdin);hidden=attrs.copy();hidden[3]&=~termios.ECHO;termios.tcsetattr(sys.stdin,termios.TCSANOW,hidden)
print('Ready for source credential JSON on hidden stdin.',flush=True)
try:credential=json.loads(sys.stdin.readline())
finally:termios.tcsetattr(sys.stdin,termios.TCSANOW,attrs)
env=os.environ.copy();env['GIT_TERMINAL_PROMPT']='0'
if credential.get('auth_mode')!='work_proxy':
    env.update(GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='http.extraHeader',GIT_CONFIG_VALUE_0='Authorization: Bearer '+credential['token'])
result=subprocess.run(['git','push',credential['remote_url'],'HEAD:'+credential['branch']],env=env,capture_output=True,text=True)
if result.returncode:
    print(result.stderr.replace(credential.get('token','\0'),'[redacted]'),file=sys.stderr);raise SystemExit(result.returncode)
print(json.dumps({'commit_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'pushed':True}))
