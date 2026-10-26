"""Read the public projection; never read monitoring credentials or alert queues."""
import json
import math
from pathlib import Path

LEVELS = {'ok','warning','critical','unknown'}
BACKUP_KEYS = ('backup','backup:matrix-database','backup:recovery')


def read_summary(path):
    with Path(path).open('rb') as source:
        body = source.read(16385)
    if len(body) > 16384:
        raise ValueError('Oversized status projection')
    data = json.loads(body)
    if not isinstance(data, dict) or data.get('schema') != 1 or data.get('available') is not True:
        raise ValueError('Monitoring summary unavailable')
    stamp = data.get('checked_at')
    if type(stamp) not in (int,float) or not math.isfinite(stamp):
        raise ValueError('Invalid monitoring timestamp')
    if data.get('disk','unknown') not in LEVELS:
        raise ValueError('Invalid disk summary')
    for key, maximum in [('containers',32),('http',8)]:
        entries = data.get(key)
        if not isinstance(entries,dict) or not 0 < len(entries) <= maximum:
            raise ValueError('Invalid monitoring scope')
        if any(not isinstance(k,str) or not k or len(k)>48 or v not in LEVELS for k,v in entries.items()):
            raise ValueError('Invalid service summary')
    backups = data.get('backups')
    if not isinstance(backups,dict):
        raise ValueError('Missing backup summary')
    for key in BACKUP_KEYS:
        result = backups.get(key)
        if not isinstance(result,dict) or result.get('level') not in LEVELS:
            raise ValueError('Invalid backup summary')
        age = result.get('age_hours')
        if age is not None and (type(age) not in (int,float) or not math.isfinite(age) or not 0 <= age < 1e6):
            raise ValueError('Invalid backup age')
    return data


def blank(title):
    return dict(title=title,main='--',label='MONITOR UNAVAILABLE',left='NO DATA',
                right='CHECK',footer='WAITING FOR MONITOR',status='NO DATA',level=-1)


def state(levels):
    if 'critical' in levels:return 'ALERT',-1
    if 'unknown' in levels:return 'CHECK',-1
    if 'warning' in levels:return 'WARN',-1
    return 'LIVE',0


def pages(data, now):
    if data is None or data['checked_at'] > now+300:
        return [blank('SERVICES'),blank('BACKUPS')]
    elapsed = max(0,now-data['checked_at'])
    containers,http = data['containers'],data['http']
    ctr_ok = sum(v=='ok' for v in containers.values())
    http_ok = sum(v=='ok' for v in http.values())
    levels = list(containers.values())+list(http.values())
    status,severity = state(levels)
    problems = [k for group in (containers,http) for k,v in group.items() if v!='ok']
    problem = ''.join(c if c.isascii() and (c.isalnum() or c in '-_.') else '_' for c in problems[0])[:28] if problems else ''
    services = dict(title='SERVICES',main=f'{ctr_ok+http_ok}/{len(levels)}',
                    label='SERVICE CHECKS',left=f'CTR {ctr_ok}/{len(containers)}',
                    right=f'HTTP {http_ok}/{len(http)}',footer=('CHECK '+problem if problems else 'CORE SERVICES OK'),
                    status=status,level=severity if severity else (ctr_ok+http_ok)/len(levels)*100)
    backups = data['backups']
    status,severity = state([backups[k]['level'] for k in BACKUP_KEYS])
    age = backups['backup']['age_hours']
    age = age+elapsed/3600 if age is not None else None
    main = '--' if age is None else (f'{age:.1f}h' if age<99.95 else f'{age/24:.0f}d' if age<24000 else '>999d')
    short = {'ok':'OK','warning':'WARN','critical':'FAIL','unknown':'--'}
    backup = dict(title='BACKUPS',main=main,label='LAST GOOD BACKUP',
                  left='DB '+short[backups['backup:matrix-database']['level']],
                  right='TEST '+short[backups['backup:recovery']['level']],
                  footer='BACKUP CHECKS OK' if not severity else 'CHECK BACKUP STATUS',
                  status=status,level=severity if severity else min(100,(age or 0)/36*100))
    if elapsed>900:
        for page in (services,backup):page.update(status='STALE',level=-1,footer='MONITOR DATA STALE')
    return [services,backup]
