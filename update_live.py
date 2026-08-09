import json, re, time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

BASE='https://bustimes.org'
STATION='/stations/620G600739'
OUT=Path('live.json')
TZ=ZoneInfo('Europe/London')
STANCE={'900':'1','X55':'3','X58':'4','X56':'5','X61':'5','X59':'6','X59A':'6','101':'7','101A':'7','101B':'7','102':'7','51':'8/10','X62':'8','X95':'9','M92':'11','913':'12','M90':'12','M91':'12','978':'12/13','909':'13','180':'14/16','183':'16','591':'14/16','594':'14/16','598':'14/16','G3':'14/16','LV2':'14'}

def get(url):
    req=Request(url,headers={'User-Agent':'EdinburghBusStationBoard/1.0 (+personal operational display; contact via GitHub)'})
    with urlopen(req,timeout=25) as r:return r.read().decode('utf-8','replace')

def clean(x):return re.sub(r'\s+',' ',x or '').strip()

def parse_rows(html, page_date, live=False):
    soup=BeautifulSoup(html,'html.parser'); out=[]
    table=soup.find('table')
    if not table:return out, None
    heads=[clean(x.get_text()).lower() for x in table.find_all('th')]
    has_expected=any('expected' in h for h in heads)
    for tr in table.find_all('tr'):
        td=tr.find_all('td')
        if len(td)<3:continue
        svc_a=td[0].find('a'); sched_a=td[2].find('a')
        if not svc_a or not sched_a:continue
        service=clean(svc_a.get_text()); sched=clean(sched_a.get_text())
        if not re.fullmatch(r'\d{1,2}:\d{2}',sched):continue
        to_text=clean(td[1].get_text(' ',strip=True))
        trip=urljoin(BASE,sched_a.get('href','')) if sched_a.get('href') else ''
        route=urljoin(BASE,svc_a.get('href','')) if svc_a.get('href') else ''
        expected=''
        if has_expected and len(td)>=4: expected=clean(td[3].get_text())
        out.append({'date':page_date,'time':sched,'service':service,'to':to_text,'stance':STANCE.get(service,'—'),'trip_url':trip,'route_url':route,'expected':expected})
    later=soup.find('a',string=lambda s:s and 'Later' in s)
    return out,(urljoin(BASE,later.get('href')) if later and later.get('href') else None)

def opmins(d,t,service_date):
    h,m=map(int,t.split(':')); dd=datetime.fromisoformat(d).date()
    delta=(dd-service_date).days
    return delta*1440+h*60+m

def build_schedule(service_date):
    url=f'{BASE}{STATION}?date={service_date.isoformat()}&time=12%3A00'; rows=[]; seen_pages=set()
    for _ in range(80):
        if not url or url in seen_pages:break
        seen_pages.add(url)
        q=parse_qs(urlparse(url).query); page_date=q.get('date',[service_date.isoformat()])[0]
        batch,later=parse_rows(get(url),page_date)
        for x in batch:
            om=opmins(x['date'],x['time'],service_date)
            if 720 <= om <= 1470: rows.append(x)
        if batch and max(opmins(x['date'],x['time'],service_date) for x in batch)>1470:break
        url=later; time.sleep(.15)
    uniq={}
    for x in rows:
        key=(x['date'],x['time'],x['service'],x['trip_url'] or x['to'])
        uniq[key]=x
    return sorted(uniq.values(),key=lambda x:opmins(x['date'],x['time'],service_date))

def live_now(today):
    html=get(f'{BASE}{STATION}')
    rows,_=parse_rows(html,today.isoformat(),True)
    return rows

def main():
    now=datetime.now(TZ); today=now.date()
    old={}
    if OUT.exists():
        try: old=json.loads(OUT.read_text())
        except: pass
    if old.get('service_date')==today.isoformat() and old.get('schedule'):
        schedule=old['schedule']
    else:
        schedule=build_schedule(today)
    live=live_now(today)
    payload={'service_date':today.isoformat(),'generated_at':now.isoformat(timespec='seconds'),'source':'bustimes.org Edinburgh Bus Station','station_url':f'{BASE}{STATION}','schedule':schedule,'live':live}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(f"{today}: {len(schedule)} schedule rows, {len(live)} live rows")

if __name__=='__main__':main()
