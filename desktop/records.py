"""Durable local school-success receipts and conservative legacy-log recovery."""
from datetime import date,datetime
import hashlib
import json
from pathlib import Path
import re

from .core import CHINA,UserError,legacy


def account_tag(account):return hashlib.sha256(account['student_id'].encode()).hexdigest()


def receipt_path(data,slot):return Path(data)/('receipt-'+slot+'.json')


def read_json(path):
    try:
        value=json.loads(Path(path).read_text('utf-8-sig'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError,UnicodeError):return {}


def valid_date(value,today):
    try:return isinstance(value,str) and date.fromisoformat(value).isoformat()==value and value<=today
    except ValueError:return False


def success_record(data,slot,account,today):
    receipt=read_json(receipt_path(data,slot))
    if not (receipt.get('schema')==1 and receipt.get('profile_id')==slot and
            receipt.get('account_tag')==account_tag(account) and valid_date(receipt.get('date'),today)):
        receipt={}
    old=read_json(Path(data)/('last-success.json' if slot=='primary' else 'last-success-secondary.json'))
    if not (old.get('student_id')==account['student_id'] and valid_date(old.get('date'),today)):old={}
    return receipt if receipt.get('date','')>=old.get('date','') else old


def commit_success(data,slot,account,instant,*,source='school_response',evidence=None):
    """The receipt is the commit point; a broken compatibility copy cannot lose it."""
    payload=dict(schema=1,profile_id=slot,account_tag=account_tag(account),date=instant.date().isoformat(),
                 confirmed_at=instant.isoformat(),source=source)
    if evidence:payload['evidence']=evidence
    path=receipt_path(data,slot);legacy.write_json(path,payload)
    if read_json(path)!=payload:raise UserError('学校已返回成功，但本地成功回执保存后校验失败。请在学校系统核实结果。')
    compatibility=Path(data)/('last-success.json' if slot=='primary' else 'last-success-secondary.json')
    try:
        legacy.write_json(compatibility,dict(student_id=account['student_id'],date=payload['date']))
        if read_json(compatibility)!={'student_id':account['student_id'],'date':payload['date']}:raise OSError('Compatibility verification failed')
    except (OSError,ValueError):return False
    return True


def recovery_candidate(data,slot,account,events,task,current,all_accounts):
    """Require account history + an identified complete run + matching system run."""
    if not task or task.get('state')=='Running' or task.get('last_result') not in (0,1):return None
    tag=account_tag(account)[:16];suffix=account['student_id'][-4:]
    if sum(a['student_id'][-4:]==suffix for a in all_accounts)!=1:return None
    identities=[e for e in events if e.get('profile_id')==slot and e.get('account_tag')]
    starts=[e['at'] for e in identities if e.get('account_tag')==tag]
    if not starts:return None
    first=min(starts);candidate=None
    try:last_run=datetime.fromisoformat(task.get('last_run',''))
    except (ValueError,TypeError):return None
    if last_run.tzinfo is None:last_run=last_run.replace(tzinfo=CHINA)
    last_run=last_run.astimezone(CHINA)
    confirmed=[]
    for event in identities:
        if event.get('kind')=='record_failed' and event.get('school_confirmed') is True and event.get('account_tag')==tag:
            try:
                at=datetime.fromisoformat(event['at'])
                if at.tzinfo is not None:confirmed.append(at.astimezone(CHINA))
            except (ValueError,KeyError,TypeError):pass
    if task.get('last_result')==1 and not confirmed:return None
    paths=sorted(Path(data).glob('signin-'+slot+'.log*'))
    pattern=re.compile(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ INFO (.*)$')
    for path in paths:
        if not path.is_file() or path.stat().st_size>4_000_000:continue
        raw=path.read_bytes();run_start=None
        for number,line in enumerate(raw.decode('utf-8',errors='replace').splitlines(),1):
            match=pattern.match(line)
            if not match:continue
            instant=datetime.strptime(match[1],'%Y-%m-%d %H:%M:%S').replace(tzinfo=CHINA);message=match[2]
            if '尝试执行签到' in message:
                run_start=instant if re.search(r'[（(]\*{4}'+re.escape(suffix)+r'[)）]',message) else None
            if not run_start or not message.endswith('晚寝签到成功'):continue
            system_match=instant.date()==last_run.date() and 0<=(run_start-last_run).total_seconds()<=120
            confirmed_match=task.get('last_result')==1 and any(0<=(at-instant).total_seconds()<=185 for at in confirmed)
            if not (system_match or confirmed_match):continue
            if not (0<=(instant-run_start).total_seconds()<=185) or instant>current:continue
            if run_start.isoformat()<first:continue
            if any(e.get('account_tag')!=tag and e['at']>=first for e in identities):continue
            if any(e.get('kind')=='account_removed' and e.get('profile_id')==slot and e['at']>=first for e in events):continue
            candidate=dict(instant=instant,evidence=dict(file=path.name,sha256=hashlib.sha256(raw).hexdigest(),line=number,
                task_last_run=task['last_run'],task_last_result=task['last_result']))
    return candidate
