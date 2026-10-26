"""SmallTV JSON feed. All rendering happens on the device."""
import json
import math
import os
from pathlib import Path
import shutil
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import monitor_pages
import alert_worker

PROC = Path(os.getenv('PROC_ROOT', '/proc'))
THERMAL = Path(os.getenv('THERMAL_ROOT', '/sys/class/thermal'))
DISK = os.getenv('DISK_PATH', '/')
PIHOLE = os.getenv('PIHOLE_URL', '')
MONITOR_STATUS_FILE = os.getenv('MONITOR_STATUS_FILE','/status/status.json')
INTERVAL = 15
LOCK = threading.Lock()
SNAPSHOT = None
WEATHER = None
WEATHER_URL = ('https://api.open-meteo.com/v1/forecast?latitude=53.13333&longitude=23.16433'
               '&current=temperature_2m,weather_code,is_day&timezone=Europe%2FWarsaw&timeformat=unixtime')


def read_weather(url=WEATHER_URL):
    with urllib.request.urlopen(url, timeout=8) as response:
        body = response.read(32769)
    if len(body) > 32768:
        raise ValueError('Oversized weather response')
    data = json.loads(body)
    if not isinstance(data, dict) or not isinstance(data.get('current'), dict):
        raise ValueError('Missing current weather')
    current = data['current']
    for field in ('temperature_2m', 'weather_code', 'is_day', 'time'):
        value = current.get(field)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('Invalid weather value')
    if not -90 <= current['temperature_2m'] <= 65 or current['is_day'] not in (0, 1):
        raise ValueError('Invalid weather range')
    if type(current['weather_code']) is not int or current['weather_code'] not in (0,1,2,3,45,48,51,53,55,56,57,61,63,65,66,67,71,73,75,77,80,81,82,85,86,95,96,99):
        raise ValueError('Unknown WMO code')
    now = time.time()
    if not now - 3600 <= current['time'] <= now + 300:
        raise ValueError('Weather timestamp outside freshness window')
    return current


def refresh_weather():
    global WEATHER
    while True:
        delay = 600
        try:
            current = read_weather()
            with LOCK:
                WEATHER = current
        except (OSError, ValueError, TypeError):
            delay = 60
        time.sleep(delay)


def clock_payload(snapshot, weather, now, rotate=True):
    # One native clock layout, with a weather card and two server cards.
    timestamp, pages = snapshot
    slot = (0, 0, 1, 2)[int(now // 20) % 4] if rotate else 0
    if slot > len(pages):
        slot = 0
    result = dict(city='BIALYSTOK', main='--', label='NO WEATHER', footer='WAITING FOR WEATHER',
                  weather=1, sun=0, cloud=0, precip=0,
                  screen=int(now % 120 >= 40))
    if slot:
        page = pages[slot - 1]
        visual = modern_page(page)
        result.update(city=visual['title'], weather=0, main=visual['main'])
        if slot == 1:
            try:result['main'] = f"{float(page['line1'].removeprefix('CPU temp: ').removesuffix(' C')):.0f}C"
            except ValueError:pass
            result['label'] = visual['left'].replace('RAM ', 'RAM') + ' / ' + visual['right'].removeprefix('FREE ')
            result['footer'] = page['line3'].replace('Load 1m: ', 'LOAD ') + ' / 1 MIN'
        else:
            try:result['main'] = f"{visual['level']:.0f}%" if not page['severity'] else '--'
            except (TypeError, ValueError):pass
            result['label'] = 'DNS BLOCKED'
            result['footer'] = visual['left'] + ' / ' + visual['right']
        if now - timestamp > 45 or page['severity']:
            result.update(label='CHECK DATA', footer='STALE / UNAVAILABLE')
    elif weather:
        age = now - weather['time']
        code = weather['weather_code']
        snow = code in (71,73,75,77,85,86)
        rain = code in (51,53,55,56,57,61,63,65,66,67,80,81,82,95,96,99)
        label = ('SNOW' if snow else 'THUNDER' if code >= 95 else 'RAIN' if rain else
                 'FOG' if code in (45,48) else 'CLEAR' if code == 0 else 'PARTLY CLOUDY' if code in (1,2) else 'CLOUDY')
        result.update(main=f"{weather['temperature_2m']:.0f}C", label=label,
                      sun=(1 if weather['is_day'] else 2) if code in (0,1,2) else 0,
                      cloud=int(code != 0), precip=2 if snow else int(rain),
                      footer='WEATHER ' + time.strftime('%H:%MZ',time.gmtime(weather['time'])))
        if age > 1800 or age < -300:
            result.update(label='STALE WEATHER', footer='LAST ' + time.strftime('%H:%MZ',time.gmtime(weather['time'])))
        if age > 7200 or age < -300:
            result.update(main='--', sun=0, cloud=0, precip=0)
    body = json.dumps(result, separators=(',', ':'), allow_nan=False).encode('ascii')
    if len(body) > 2048:
        raise ValueError('Firmware response limit exceeded')
    return body


def memory_percent(text):
    values = {line.split(':')[0]: int(line.split()[1])
              for line in text.splitlines() if line.startswith(('MemTotal:', 'MemAvailable:'))}
    return round(100 * (1 - values['MemAvailable'] / values['MemTotal']))


def pihole_summary(url):
    # The URL comes from operator configuration, never a request parameter.
    with urllib.request.urlopen(url, timeout=3) as response:
        payload = response.read(4097)
    if len(payload) > 4096:
        raise ValueError('Oversized Pi-hole response')
    data = json.loads(payload)
    if not isinstance(data, dict) or data.get('status') != 'online':
        raise ValueError('Pi-hole adapter unavailable')
    for key in ('queries_total', 'queries_blocked', 'percent_blocked', 'unique_clients'):
        value = data[key]
        if type(value) not in (int, float) or not 0 <= value < 1e12:
            raise ValueError('Invalid Pi-hole metric')
    return data


def collect():
    timestamp = time.time()
    pi = dict(title='RASPBERRY PI 5', line1='CPU temp: --', line2='RAM: --',
              line3='Load: --', line4='Disk: --', severity=0)
    readers = {
        'line1': lambda: f"CPU temp: {int((THERMAL/'thermal_zone0/temp').read_text()) / 1000:.1f} C",
        'line2': lambda: f"RAM used: {memory_percent((PROC/'meminfo').read_text())}%",
        'line3': lambda: f"Load 1m: {(PROC/'loadavg').read_text().split()[0]}",
        'line4': lambda: f"Disk free: {shutil.disk_usage(DISK).free / 1024**3:.1f}G",
    }
    for key, reader in readers.items():
        try:
            pi[key] = reader()
        except (OSError, ValueError, KeyError, ZeroDivisionError, IndexError):
            pi['severity'] = 1
    pages = [pi]
    if PIHOLE:
        page = dict(title='PI-HOLE', line1='Data unavailable', line2='Check adapter',
                    line3='', line4='', severity=1)
        try:
            data = pihole_summary(PIHOLE)
            page.update(line1=f"Queries: {data['queries_total']:.0f}",
                        line2=f"Blocked: {data['queries_blocked']:.0f}",
                        line3=f"Blocked: {data['percent_blocked']:.1f}%",
                        line4=f"Clients: {data['unique_clients']:.0f}", severity=0)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        pages.append(page)
    return timestamp, pages


def modern_page(page):
    """Presentation adapter for the existing, server-owned metric page format."""
    pi = page['title'] == 'RASPBERRY PI 5'
    result = dict(title='RASPBERRY PI' if pi else 'PI-HOLE', main='--',
                  label='CPU TEMPERATURE' if pi else 'DNS QUERIES BLOCKED',
                  left='RAM --' if pi else 'QUERIES --',
                  right='FREE --' if pi else 'CLIENTS --', level=0)
    if pi:
        try:
            value = float(page['line1'].removeprefix('CPU temp: ').removesuffix(' C'))
            result.update(main=(f'{value:.1f}' if value < 100 else f'{value:.0f}') + 'C', level=value)
        except ValueError:
            pass
        result['left'] = page['line2'].replace('RAM used: ', 'RAM ')
        result['right'] = page['line4'].replace('Disk free: ', 'FREE ')
    elif not page['severity']:
        value = float(page['line3'].removeprefix('Blocked: ').removesuffix('%'))
        result.update(main=(f'{value:.1f}' if value < 100 else f'{value:.0f}') + '%', level=value)
        queries = float(page['line1'].removeprefix('Queries: '))
        compact = f'{queries / 1e6:.1f}M' if queries >= 1e6 else (f'{queries / 1000:.1f}K' if queries >= 1000 else f'{queries:.0f}')
        result['left'] = compact + ' DNS'
        result['right'] = page['line4'].replace('Clients: ', '') + ' CLIENTS'
    return result


def payload(snapshot, now, modern=False):
    timestamp, pages = snapshot
    page = dict(pages[int(now // 20) % len(pages)])
    stale = now - timestamp > 45
    page['status'] = 'STALE' if stale else ('CHECK' if page['severity'] else 'LIVE')
    page['severity'] = max(page['severity'], int(stale))
    page['updated'] = time.strftime('%H:%M:%S UTC', time.gmtime(timestamp))
    if modern:
        visual = modern_page(page)
        visual['status'] = page['status']
        if page['severity']:
            visual['level'] = -1
        stamp = time.strftime('%H:%MZ', time.gmtime(timestamp))
        load = page.get('line3', '').removeprefix('Load 1m: ')
        visual['footer'] = ('LOAD ' + load + '  /  ' + stamp
                            if page['title'] == 'RASPBERRY PI 5' else 'DNS PROTECTION  /  ' + stamp)
        if stale:
            visual['footer'] = 'STALE DATA  /  ' + stamp
        page = visual
    result = json.dumps(page, separators=(',', ':'), allow_nan=False).encode('ascii')
    if len(result) > 2048:
        raise ValueError('Firmware response limit exceeded')
    return result


def dashboard_payload(snapshot, monitoring, now):
    slot = int(now % 120 // 20)
    if slot <= 3:
        index = 1 if slot == 3 else 0
        timestamp, items = snapshot
        if index < len(items):
            return payload((timestamp,[items[index]]),now,modern=True)
        page = monitor_pages.blank('PI-HOLE')
    else:
        page = monitor_pages.pages(monitoring,now)[slot-4]
    return json.dumps(page,separators=(',',':'),allow_nan=False).encode('ascii')


def refresh():
    global SNAPSHOT
    while True:
        snapshot = collect()
        with LOCK:
            SNAPSHOT = snapshot
        time.sleep(INTERVAL)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/screen.json', '/screen-v2.json', '/dashboard.json', '/clock.json', '/home.json', '/notifications.json', '/health'):
            self.send_error(404)
            return
        with LOCK:
            snapshot = SNAPSHOT
            weather = WEATHER
        if snapshot is None:
            self.send_error(503)
            return
        if self.path == '/health':
            stale = time.time() - snapshot[0] > 45
            body = b'{"ok":false}' if stale else b'{"ok":true}'
            self.send_response(503 if stale else 200)
        else:
            if self.path == '/notifications.json':
                body=json.dumps(alert_worker.STATUS,separators=(',',':')).encode('ascii')
            elif self.path == '/dashboard.json':
                try:
                    monitoring = monitor_pages.read_summary(MONITOR_STATUS_FILE)
                except (OSError,ValueError,TypeError,KeyError):
                    monitoring = None
                body = dashboard_payload(snapshot,monitoring,time.time())
            else:
                body = (clock_payload(snapshot, weather, time.time(), rotate=self.path == '/home.json')
                        if self.path in ('/clock.json', '/home.json')
                        else payload(snapshot, time.time(), modern=self.path == '/screen-v2.json'))
            self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


if __name__ == '__main__':
    threading.Thread(target=refresh, daemon=True).start()
    threading.Thread(target=refresh_weather, daemon=True).start()
    if os.getenv('SMALLTV_DEVICE_URL'):
        threading.Thread(target=alert_worker.run,args=(MONITOR_STATUS_FILE,
            os.getenv('ALERT_STATE_FILE','/state/alerts.json'),os.environ['SMALLTV_DEVICE_URL']),daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT', '8096'))), Handler).serve_forever()
