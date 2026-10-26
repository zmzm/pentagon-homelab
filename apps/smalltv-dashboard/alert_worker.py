"""Bounded SmallTV overlays with persistent deduplication and quiet hours."""
import copy
from datetime import datetime
import fcntl
from http.client import HTTPException
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

import monitor_pages

REMINDER_SECONDS = 6*3600
LEVELS = {'ok','warning','critical','unknown'}
STATUS = {'enabled':False,'state':'not-started'}


def quiet_hours(now):
    hour = datetime.fromtimestamp(now,ZoneInfo('Europe/Warsaw')).hour
    return hour>=23 or hour<7


def observations(data,now):
    if data is None:
        return {'monitor':{'level':'warning','label':'Monitor data missing'}}
    if not -300 <= now-data['checked_at'] <= 900:
        return {'monitor':{'level':'warning','label':'Monitor data stale'}}
    result = {'monitor':{'level':'ok','label':'Monitoring'},
              'disk':{'level':data.get('disk','unknown'),'label':'Disk space'}}
    for group in ('containers','http'):
        for name,level in data[group].items():
            safe = re.sub(r'[^A-Za-z0-9_.-]','_',name)[:32]
            result[group+':'+safe]={'level':level,'label':safe+(' health' if group=='http' else '')}
    names = {'backup':'Backups','backup:matrix-database':'Database backup','backup:recovery':'Restore test'}
    for key,name in names.items():result[key]={'level':data['backups'][key]['level'],'label':name}
    return result


def save_state(path,state):
    path=Path(path);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as output:
            temporary=Path(output.name);os.fchmod(output.fileno(),0o600)
            json.dump(state,output,separators=(',',':'),allow_nan=False)
            output.flush();os.fsync(output.fileno())
        os.replace(temporary,path)
        descriptor=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
    finally:
        if temporary is not None and temporary.exists():temporary.unlink()


def load_state(path):
    try:
        with Path(path).open('rb') as source:body=source.read(65537)
    except FileNotFoundError:
        return {'schema':1,'checks':{},'retry_after':0}
    if len(body)>65536:raise ValueError('Oversized alert state')
    state=json.loads(body)
    if not isinstance(state,dict) or state.get('schema')!=1 or not isinstance(state.get('checks'),dict) or len(state['checks'])>128:
        raise ValueError('Invalid alert state')
    for entry in state['checks'].values():
        if not isinstance(entry,dict) or entry.get('level') not in LEVELS or entry.get('delivery') not in ('claimed','confirmed','uncertain','rejected'):
            raise ValueError('Invalid persisted alert')
        stamp=entry.get('attempted_at')
        if type(stamp) not in (int,float) or not math.isfinite(stamp):raise ValueError('Invalid alert timestamp')
    retry=state.get('retry_after',0)
    if type(retry) not in (int,float) or not math.isfinite(retry):raise ValueError('Invalid retry timestamp')
    return state


def plan(state,current,now):
    candidates={}
    for key,item in current.items():
        old=state['checks'].get(key,{'level':'ok','attempted_at':0})
        changed=old['level']!=item['level']
        reminder=item['level']!='ok' and now-old['attempted_at']>=REMINDER_SECONDS
        if changed or reminder:candidates[key]=item
    problems={k:v for k,v in candidates.items() if v['level']!='ok'}
    criticals={k:v for k,v in problems.items() if v['level']=='critical'}
    chosen=criticals or problems or candidates
    if not chosen:return None
    critical=any(v['level']=='critical' for v in chosen.values())
    recovered=not problems
    labels=[v['label'] for v in chosen.values()]
    shown=[]
    for label in labels:
        if len(', '.join(shown+[label]))>40:break
        shown.append(label)
    label=', '.join(shown) or labels[0][:40]
    if len(shown)<len(labels):label+=' +'+str(len(labels)-len(shown))
    payload={'type':'info' if recovered else 'alert' if critical else 'warning',
             'title':'RECOVERED' if recovered else 'HOMELAB ALERT' if critical else 'HOMELAB WARNING',
             'label':label,'ttl':8 if recovered else 15,'priority':0 if recovered else 2 if critical else 1}
    if recovered:payload['color']='#43CC88'
    return chosen,payload


def device_ready(url):
    with urllib.request.urlopen(url+'/api/status',timeout=3) as response:
        data=json.loads(response.read(16384))
    if not isinstance(data,dict) or data.get('fw')!='smalltv-mod' or not data.get('connected'):
        raise ValueError('Device unavailable')


def send_notification(url,payload):
    request=urllib.request.Request(url+'/api/notify',data=json.dumps(payload).encode(),
        headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(request,timeout=5) as response:
        result=json.loads(response.read(2048))
    if not isinstance(result,dict) or result.get('ok') is not True:raise ValueError('Notification not acknowledged')


def tick(path,current,now,quiet,preflight,send):
    state=load_state(path)
    if quiet or now<state.get('retry_after',0):return 'quiet' if quiet else 'backoff'
    event=plan(state,current,now)
    if event is None:return 'unchanged'
    chosen,payload=event
    try:preflight()
    except (OSError,ValueError,HTTPException):return 'offline'  # No write was attempted.
    before=copy.deepcopy(state)
    for key,item in chosen.items():
        state['checks'][key]={'level':item['level'],'attempted_at':now,'delivery':'claimed'}
    save_state(path,state)  # Claim before dispatch; interrupted claims are never replayed immediately.
    outcome='confirmed'
    try:
        send(payload)
    except urllib.error.HTTPError as error:
        if error.code==429:
            before['retry_after']=now+60;save_state(path,before);return 'queue-full'
        outcome='rejected' if 400<=error.code<500 else 'uncertain'
    except (OSError,ValueError,HTTPException):outcome='uncertain'
    for key in chosen:state['checks'][key]['delivery']=outcome
    state['last_delivery']={'at':now,'outcome':outcome,'count':len(chosen)}
    save_state(path,state)
    return outcome


def run(status_file,state_file,device_url):
    global STATUS
    path=Path(state_file);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    # One cooperating worker per state directory, including across container restarts.
    with (path.parent/'alerts.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            initial=load_state(path)  # Corruption does not reset deduplication.
            if not path.exists():save_state(path,initial)
        except (OSError,ValueError,TypeError):
            STATUS={'enabled':False,'state':'storage-error'}
            print('SmallTV notifications stopped: invalid state',flush=True)
            return
        while True:
            try:
                try:data=monitor_pages.read_summary(status_file)
                except (OSError,ValueError,TypeError,KeyError):data=None
                now=time.time()
                result=tick(path,observations(data,now),now,quiet_hours(now),
                    lambda:device_ready(device_url),lambda payload:send_notification(device_url,payload))
                STATUS={'enabled':True,'state':result,'checked_at':now,
                        'last_delivery':load_state(path).get('last_delivery')}
                if result not in ('quiet','unchanged','backoff'):
                    print('SmallTV notification: '+result,flush=True)
            except (OSError,ValueError,TypeError,KeyError):
                STATUS={'enabled':False,'state':'storage-error'}
                print('SmallTV notifications stopped: state or storage error',flush=True)
                return
            time.sleep(15)
