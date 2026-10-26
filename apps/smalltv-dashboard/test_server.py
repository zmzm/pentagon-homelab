import io
import json
import unittest
from unittest.mock import patch
import server


class FeedTests(unittest.TestCase):
    def test_memory_uses_available_including_reclaimable_memory(self):
        self.assertEqual(server.memory_percent('MemTotal: 1000 kB\nMemFree: 100 kB\nMemAvailable: 600 kB\n'), 40)

    def test_stale_snapshot_is_labeled_and_keeps_original_timestamp(self):
        snapshot = (100, [dict(title='PI', severity=0)])
        data = json.loads(server.payload(snapshot, 200))
        self.assertEqual(data['status'], 'STALE')
        self.assertEqual(data['severity'], 1)
        self.assertEqual(data['updated'], '00:01:40 UTC')
        self.assertNotIn('status', snapshot[1][0])

    def test_unavailable_pihole_is_not_zero_success(self):
        with patch.object(server, 'PIHOLE', 'http://adapter/'), patch.object(server, 'pihole_summary', side_effect=OSError):
            _, pages = server.collect()
        self.assertEqual(pages[1]['severity'], 1)
        self.assertEqual(pages[1]['line1'], 'Data unavailable')

    def test_valid_adapter_contract(self):
        data = dict(status='online', queries_total=10, queries_blocked=3,
                    percent_blocked=30, unique_clients=2)
        with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(data).encode())):
            self.assertEqual(server.pihole_summary('http://adapter/'), data)

    def test_rejects_oversized_and_invalid_metrics(self):
        for body in (b'x' * 4097, b'{"status":"online","queries_total":NaN}'):
            with self.subTest(body=body[:50]), patch('urllib.request.urlopen', return_value=io.BytesIO(body)):
                with self.assertRaises(ValueError):
                    server.pihole_summary('http://adapter/')

    def test_rotation_and_response_size(self):
        pages = [dict(title='PI', severity=0), dict(title='DNS', severity=0)]
        self.assertEqual(json.loads(server.payload((0, pages), 0))['title'], 'PI')
        self.assertEqual(json.loads(server.payload((0, pages), 20))['title'], 'DNS')
        self.assertLess(len(server.payload((0, pages), 20)), 2048)

    def test_modern_pi_uses_compact_values_and_keeps_stale_warning(self):
        page = dict(title='RASPBERRY PI 5', line1='CPU temp: 52.4 C',
                    line2='RAM used: 26%', line3='Load 1m: 0.32',
                    line4='Disk free: 11.1G', severity=0)
        data = json.loads(server.payload((100, [page]), 110, modern=True))
        self.assertEqual(data['main'], '52.4C')
        self.assertEqual(data['level'], 52.4)
        self.assertEqual(data['left'], 'RAM 26%')
        self.assertEqual(len(data), 8)
        stale = json.loads(server.payload((100, [page]), 200, modern=True))
        self.assertEqual(stale['status'], 'STALE')
        self.assertTrue(stale['footer'].startswith('STALE DATA'))

    def test_modern_dns_formats_full_percentage_and_handles_unavailable_data(self):
        page = dict(title='PI-HOLE', line1='Queries: 18848', line2='Blocked: 18848',
                    line3='Blocked: 100.0%', line4='Clients: 4', severity=0)
        data = json.loads(server.payload((100, [page]), 110, modern=True))
        self.assertEqual(data['main'], '100%')
        self.assertEqual(data['left'], '18.8K DNS')
        page.update(severity=1, line1='Data unavailable', line3='')
        data = json.loads(server.payload((100, [page]), 110, modern=True))
        self.assertEqual(data['main'], '--')
        self.assertEqual(data['status'], 'CHECK')

    def test_weather_validates_source_timestamp_and_numeric_values(self):
        valid = dict(current=dict(time=1000000, temperature_2m=8.0, weather_code=51, is_day=1))
        with patch('time.time', return_value=1000000), patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(valid).encode())):
            self.assertEqual(server.read_weather()['temperature_2m'], 8)
        for changes in ({'time': 990000}, {'weather_code': 500}, {'temperature_2m': None}):
            data = dict(current=valid['current'] | changes)
            with self.subTest(changes=changes), patch('time.time', return_value=1000000), patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(data).encode())):
                with self.assertRaises(ValueError):server.read_weather()

    def test_clock_weather_icons_and_bounded_contract(self):
        snapshot = (1000000, [])
        for code, day, expected in [(0,1,(1,0,0)), (0,0,(2,0,0)), (3,1,(0,1,0)), (61,1,(0,1,1)), (75,1,(0,1,2))]:
            weather = dict(time=1000000, temperature_2m=-8.2, weather_code=code, is_day=day)
            data = json.loads(server.clock_payload(snapshot, weather, 1000010, rotate=False))
            self.assertEqual((data['sun'],data['cloud'],data['precip']),expected)
            self.assertEqual(data['main'],'-8C')
            self.assertEqual(len(data),9)
            self.assertNotIn('time',data)  # Native clock keeps time without network updates.

    def test_weather_missing_stale_and_expired_are_distinct(self):
        snapshot = (1000000, [])
        data = json.loads(server.clock_payload(snapshot, None, 1000010, rotate=False))
        self.assertEqual(data['main'],'--')
        weather = dict(time=1000000, temperature_2m=8, weather_code=0, is_day=1)
        stale = json.loads(server.clock_payload(snapshot,weather,1002000,rotate=False))
        expired = json.loads(server.clock_payload(snapshot,weather,1008000,rotate=False))
        self.assertEqual(stale['label'],'STALE WEATHER')
        self.assertEqual(stale['main'],'8C')
        self.assertEqual(expired['main'],'--')
        self.assertEqual(expired['sun'],0)

    def test_clock_carousel_keeps_both_server_pages(self):
        pages = [dict(title='RASPBERRY PI 5',line1='CPU temp: 53.0 C',line2='RAM used: 25%',line3='Load 1m: 0.3',line4='Disk free: 11.1G',severity=0),
                 dict(title='PI-HOLE',line1='Queries: 18848',line2='Blocked: 1884',line3='Blocked: 10.0%',line4='Clients: 4',severity=0)]
        names = [json.loads(server.clock_payload((t,pages),None,t))['city'] for t in (0,20,40,60)]
        self.assertEqual(names,['BIALYSTOK','BIALYSTOK','RASPBERRY PI','PI-HOLE'])

    def test_separate_layout_phase_matches_original_metric_rotation(self):
        snapshot = (0, [])
        phases = [json.loads(server.clock_payload(snapshot,None,t,rotate=False))['screen']
                  for t in (0,39,40,59,60,79,80,100,119,120)]
        self.assertEqual(phases,[0,0,1,1,1,1,1,1,1,0])


if __name__ == '__main__':
    unittest.main()
