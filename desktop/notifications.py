"""Resident-only result notifications, without replaying historical events."""
from datetime import datetime
import hashlib
import json


class EventNotifications:
    def __init__(self, started):
        self.started=started
        self.seen=set()

    def consume(self, entries, preferences, source='local'):
        result=[]
        if not isinstance(entries,list): return result
        for entry in reversed(entries):
            if not isinstance(entry,dict): continue
            key=hashlib.sha256((source+json.dumps(entry,sort_keys=True,ensure_ascii=False)).encode()).hexdigest()
            if key in self.seen: continue
            self.seen.add(key)
            try:
                at=datetime.fromisoformat(entry.get('at',''))
                if at.tzinfo is None or at<self.started: continue
            except (ValueError,TypeError): continue
            kind=entry.get('kind')
            preference_kind='failed' if kind=='record_failed' else kind
            if not preferences['notifications'] or kind not in ('success','failed','mode','record_failed') or not preferences.get('notify_'+preference_kind,False): continue
            endpoint='VPS' if source=='cloud' or entry.get('mode')=='cloud' else '本机'
            if kind=='success': title,body='签到成功',endpoint+'：学校系统已确认今日签到成功。'
            elif kind=='failed': title,body='签到未成功',endpoint+'：未收到学校成功确认，请打开运行记录查看。'
            elif kind=='record_failed':title,body='本地回执保存失败',endpoint+'：学校已返回成功，但本地记录未保存，请核实学校结果并检查数据目录权限。'
            else: title,body='执行端已切换','当前由 '+endpoint+' 执行每日计划。'
            if entry.get('account_label'):
                body=entry['account_label']+'\n'+body
                if kind=='mode':title,body='账号计划已启用',entry['account_label']+'\n'+entry.get('message','')
            result.append((title,body,kind in ('failed','record_failed')))
        # A bounded recent history is enough for deduplication across log rotation.
        if len(self.seen)>4000:
            self.seen={hashlib.sha256((source+json.dumps(e,sort_keys=True,ensure_ascii=False)).encode()).hexdigest() for e in entries if isinstance(e,dict)}
        return result
