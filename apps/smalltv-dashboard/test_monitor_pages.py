import copy
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import unittest

import export_monitor
import monitor_pages
import server


def fixture():
    return {'checked_at':datetime.fromtimestamp(1000000,timezone.utc).isoformat(),
            'checks':{'container:caddy':{'level':'ok','message':'TOKEN-secret'},
                      'http:matrix':{'level':'ok','message':'PRIVATE-log'},
                      'backup':{'level':'ok','message':'Latest successful backup is 6.9 hours old'},
                      'backup:matrix-database':{'level':'ok','message':'Matrix database dump is 0.9 hours old'},
                      'backup:recovery':{'level':'ok','message':'Last successful recovery verification is 31.4 hours old'},
                      'http:unlisted':{'level':'critical','message':'do-not-publish'}},
            'pending':[{'body':'SECRET-ALERT-QUEUE'}]}


CONFIG = {'containers':['caddy'],'http':[{'id':'matrix','url':'SECRET-URL'}]}


class MonitorProjectionTests(unittest.TestCase):
    def test_projection_excludes_raw_messages_queue_config_urls_and_unlisted_checks(self):
        data = export_monitor.summary(fixture(),CONFIG)
        text = json.dumps(data)
        for secret in ['TOKEN-secret','PRIVATE-log','SECRET-ALERT-QUEUE','SECRET-URL','unlisted']:
            self.assertNotIn(secret,text)
        self.assertEqual(data['containers'],{'caddy':'ok'})
        self.assertEqual(data['backups']['backup']['age_hours'],6.9)

    def test_missing_checks_never_become_healthy_and_initial_restore_is_not_success(self):
        value=fixture();value['checks'].pop('container:caddy')
        value['checks']['backup:recovery']['message']='Initial recovery verification is running'
        data=export_monitor.summary(value,CONFIG)
        self.assertEqual(data['containers']['caddy'],'unknown')
        self.assertEqual(data['backups']['backup:recovery']['level'],'unknown')
        services,backup=monitor_pages.pages(data,1000010)
        self.assertEqual(services['main'],'1/2')
        self.assertEqual(backup['right'],'TEST --')
        self.assertEqual(backup['status'],'CHECK')

    def test_private_error_text_is_not_published_as_backup_age(self):
        value=fixture();value['checks']['backup']={'level':'critical','message':'Failed URL with SECRET token'}
        data=export_monitor.summary(value,CONFIG)
        self.assertIsNone(data['backups']['backup']['age_hours'])
        page=monitor_pages.pages(data,1000010)[1]
        self.assertEqual(page['main'],'--')
        self.assertEqual(page['status'],'ALERT')
        self.assertNotIn('SECRET',json.dumps(data))

    def test_public_file_is_readable_and_replacement_is_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'status.json'
            export_monitor.publish(path,export_monitor.summary(fixture(),CONFIG))
            self.assertEqual(path.stat().st_mode & 0o777,0o644)
            self.assertTrue(monitor_pages.read_summary(path)['available'])
            export_monitor.publish(path,{'schema':1,'available':False})
            with self.assertRaises(ValueError):monitor_pages.read_summary(path)

    def test_malformed_summary_cannot_render_healthy(self):
        for mutation in [{'checked_at':float('nan')},{'containers':{}},{'backups':{}},{'schema':2}]:
            data=export_monitor.summary(fixture(),CONFIG)|mutation
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'status.json';path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):monitor_pages.read_summary(path)

    def test_stale_and_future_snapshots_are_explicit(self):
        data=export_monitor.summary(fixture(),CONFIG)
        for page in monitor_pages.pages(data,1001000):self.assertEqual(page['status'],'STALE')
        for page in monitor_pages.pages(data,999000):self.assertEqual(page['main'],'--')

    def test_backup_age_advances_from_source_check_time_and_fits_the_hero(self):
        data=export_monitor.summary(fixture(),CONFIG)
        self.assertEqual(monitor_pages.pages(data,1000360)[1]['main'],'7.0h')
        for age in (99.94,99.96,100,24000,999999):
            data['backups']['backup']['age_hours']=age
            self.assertLessEqual(len(monitor_pages.pages(data,1000000)[1]['main']),5)

    def test_carousel_adds_pages_without_changing_original_metric_values(self):
        data=export_monitor.summary(fixture(),CONFIG)
        pi=dict(title='RASPBERRY PI 5',line1='CPU temp: 53.0 C',line2='RAM used: 25%',line3='Load 1m: 0.3',line4='Disk free: 11.1G',severity=0)
        dns=dict(title='PI-HOLE',line1='Queries: 18000',line2='Blocked: 1800',line3='Blocked: 10.0%',line4='Clients: 4',severity=0)
        snapshot=(1000000,[pi,dns])
        for now,index in [(1000000//120*120+40,0),(1000000//120*120+60,1)]:
            self.assertEqual(server.dashboard_payload(snapshot,data,now),server.payload((snapshot[0],[snapshot[1][index]]),now,modern=True))
        titles=[json.loads(server.dashboard_payload(snapshot,data,1200000+t))['title'] for t in (40,60,80,100)]
        self.assertEqual(titles,['RASPBERRY PI','PI-HOLE','SERVICES','BACKUPS'])
        for t in (80,100):
            page=json.loads(server.dashboard_payload(snapshot,None,1200000+t))
            self.assertEqual(page['main'],'--')
            self.assertLess(len(json.dumps(page)),2048)


if __name__ == '__main__':unittest.main()
