from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

def now_jst():
    return datetime.now(JST)

def parse_jst_time(timestr: str):
    return datetime.fromisoformat(timestr)
