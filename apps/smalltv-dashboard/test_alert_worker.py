from datetime import datetime,timezone
from http.client import IncompleteRead
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import urllib.error
from zoneinfo import ZoneInfo

import alert_worker as alerts


class AlertTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'alerts.json'
        self.ready=Mock();self.send=Mock()
        self.bad={'service':{'level':'critical','label':'Matrix'}}

    def tick(self,current=None,now=1000000,quiet=False):
        return alerts.tick(self.path,self.bad if current is None else current,now,quiet,self.ready,self.send)

    def test_new_alert_is_claimed_before_dispatch_and_deduplicated_across_restart(self):
        def effect(payload):
            self.assertEqual(alerts.load_state(self.path)['checks']['service']['delivery'],'claimed')
            self.assertEqual(payload['type'],'alert')
        self.send.side_effect=effect
        self.assertEqual(self.tick(),'confirmed')
        self.assertEqual(self.tick(now=1000015),'unchanged')
        self.assertEqual(self.send.call_count,1)
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)
        self.assertEqual(self.tick(now=1000000+alerts.REMINDER_SECONDS),'confirmed')

    def test_healthy_startup_does_not_send_recovery_and_recovery_after_alert_is_green(self):
        good={'service':{'level':'ok','label':'Matrix'}}
        self.assertEqual(self.tick(good),'unchanged')
        self.tick();self.tick(good,now=1000015)
        payload=self.send.call_args.args[0]
        self.assertEqual(payload['title'],'RECOVERED')
        self.assertEqual(payload['color'],'#43CC88')

    def test_quiet_hours_suppress_network_and_show_only_still_current_problems_in_morning(self):
        self.assertEqual(self.tick(quiet=True),'quiet')
        self.ready.assert_not_called();self.send.assert_not_called()
        self.assertFalse(self.path.exists())
        self.assertEqual(self.tick({'service':{'level':'ok','label':'Matrix'}},now=1000100),'unchanged')
        self.assertEqual(self.tick(now=1000115),'confirmed')

    def test_quiet_window_and_daylight_saving_time(self):
        for day in ('2026-01-15','2026-07-15','2026-10-26'):
            for clock,expected in [('22:59',False),('23:00',True),('00:00',True),('06:59',True),('07:00',False)]:
                stamp=datetime.fromisoformat(day+'T'+clock).replace(tzinfo=ZoneInfo('Europe/Warsaw')).timestamp()
                self.assertEqual(alerts.quiet_hours(stamp),expected,(day,clock))

    def test_failed_preflight_does_not_consume_event_and_retries_read_later(self):
        self.ready.side_effect=TimeoutError()
        self.assertEqual(self.tick(),'offline')
        self.send.assert_not_called();self.assertFalse(self.path.exists())
        self.ready.side_effect=None
        self.assertEqual(self.tick(now=1000015),'confirmed')

    def test_unknown_post_outcome_and_interrupted_claim_are_not_replayed(self):
        self.send.side_effect=IncompleteRead(b'',3)
        self.assertEqual(self.tick(),'uncertain')
        self.send.side_effect=None
        self.assertEqual(self.tick(now=1000015),'unchanged')
        state=alerts.load_state(self.path);state['checks']['service']['delivery']='claimed';alerts.save_state(self.path,state)
        self.assertEqual(self.tick(now=1000030),'unchanged')
        self.assertEqual(self.send.call_count,1)

    def test_queue_rejection_backs_off_without_claiming_delivery(self):
        self.send.side_effect=urllib.error.HTTPError('http://device',429,'Full',{},io.BytesIO(b''))
        self.assertEqual(self.tick(),'queue-full')
        self.assertEqual(alerts.load_state(self.path)['checks'],{})
        self.assertEqual(self.tick(now=1000030),'backoff')
        self.send.side_effect=None
        self.assertEqual(self.tick(now=1000060),'confirmed')

    def test_critical_precedes_warning_and_storage_failure_prevents_dispatch(self):
        mixed=self.bad|{'disk':{'level':'warning','label':'Disk'}}
        self.tick(mixed)
        self.assertEqual(self.send.call_args.args[0]['label'],'Matrix')
        self.tick(mixed,now=1000015)
        self.assertEqual(self.send.call_args.args[0]['type'],'warning')
        self.path.write_text('{broken')
        with self.assertRaises(ValueError):self.tick(now=1000030)
        self.assertEqual(self.send.call_count,2)

    def test_unavailable_monitor_does_not_create_fake_service_recovery(self):
        observations=alerts.observations(None,1000000)
        self.assertEqual(set(observations),{'monitor'})
        self.assertEqual(observations['monitor']['level'],'warning')


if __name__ == '__main__':unittest.main()
