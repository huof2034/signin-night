"""Verified Task Scheduler COM operations, one PowerShell process per save."""
from datetime import datetime
from pathlib import Path
import json
import xml.etree.ElementTree as ET


COM = r'''
$svc=New-Object -ComObject 'Schedule.Service';$svc.Connect();$folder=$svc.GetFolder('\')
function Find-Task($name){
 try{return $folder.GetTask($name)}catch{
  if(($_.Exception.HResult -band 65535) -eq 2 -or ($_.Exception.InnerException.HResult -band 65535) -eq 2 -or $_.Exception.Message -match '80070002'){return $null}
  throw
 }
}
function Task-Info($t){
 if(-not $t){return $null}
 $d=$t.Definition;$trigger=$d.Triggers.Item(1);$action=$d.Actions.Item(1)
 $states=@('Unknown','Disabled','Queued','Ready','Running')
 $boundary=[string]$trigger.StartBoundary
 $time=if($boundary.Length -ge 16){$boundary.Substring(11,5)}else{''}
 return @{state=$states[[int]$t.State];enabled=[bool]$t.Enabled;next_run=$t.NextRunTime.ToString('o');last_run=$t.LastRunTime.ToString('o');last_result=$t.LastTaskResult;
  schedule_time=$time;beijing=$boundary.EndsWith('+08:00');worker=[string]$action.Path;arguments=[string]$action.Arguments;
  description=[string]$d.RegistrationInfo.Description;action_count=$d.Actions.Count;trigger_count=$d.Triggers.Count}
}
'''


def task_xml(scheduled, enabled, executable, arguments, description):
    from .core import now
    ns='http://schemas.microsoft.com/windows/2004/02/mit/task'
    ET.register_namespace('',ns)
    def add(parent,name,value=None,**attrs):
        item=ET.SubElement(parent,'{'+ns+'}'+name,attrs)
        if value is not None:item.text=str(value)
        return item
    root=ET.Element('{'+ns+'}Task',version='1.4')
    add(add(root,'RegistrationInfo'),'Description',description)
    trigger=add(add(root,'Triggers'),'CalendarTrigger')
    add(trigger,'StartBoundary',now().date().isoformat()+'T'+scheduled+':00+08:00')
    add(trigger,'Enabled','true');add(add(trigger,'ScheduleByDay'),'DaysInterval','1')
    principal=add(add(root,'Principals'),'Principal',id='Author')
    add(principal,'UserId','__CURRENT_SID__');add(principal,'LogonType','InteractiveToken');add(principal,'RunLevel','LeastPrivilege')
    settings=add(root,'Settings')
    for key,value in [('MultipleInstancesPolicy','IgnoreNew'),('DisallowStartIfOnBatteries','false'),('StopIfGoingOnBatteries','false'),
                      ('AllowHardTerminate','true'),('StartWhenAvailable','false'),('RunOnlyIfNetworkAvailable','false')]:add(settings,key,value)
    idle=add(settings,'IdleSettings');add(idle,'StopOnIdleEnd','false');add(idle,'RestartOnIdle','false')
    for key,value in [('AllowStartOnDemand','true'),('Enabled',str(bool(enabled)).lower()),('Hidden','false'),('RunOnlyIfIdle','false'),
                      ('WakeToRun','true'),('ExecutionTimeLimit','PT5M'),('Priority','7')]:add(settings,key,value)
    action=add(add(root,'Actions',Context='Author'),'Exec');add(action,'Command',executable);add(action,'Arguments',arguments)
    return ET.tostring(root,encoding='unicode')


def info(task):
    from .core import ps,quote_ps
    result=ps(COM+f'\nTask-Info (Find-Task {quote_ps(task.name)}) | ConvertTo-Json -Depth 3 -Compress')
    return json.loads(result.stdout.strip() or 'null')


def apply(task, scheduled, enabled, executable, arguments):
    from .core import ps,quote_ps,TASK_DESCRIPTION,UserError
    xml=task_xml(scheduled,enabled,executable,arguments,TASK_DESCRIPTION)
    script=COM+f'''
$name={quote_ps(task.name)};$description={quote_ps(TASK_DESCRIPTION)}
$old=Find-Task $name
if($old -and $old.Definition.RegistrationInfo.Description -ne $description){{throw 'Conflicting scheduled task'}}
$before=if($old){{[string]$old.Xml}}else{{$null}}
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$xml={quote_ps(xml)}.Replace('__CURRENT_SID__',$sid)
try{{
 $t=$folder.RegisterTask($name,$xml,6,$sid,$null,3,$null)
 $actual=Task-Info $t
 if($actual.enabled -ne ${str(bool(enabled)).lower()} -or $actual.schedule_time -ne {quote_ps(scheduled)} -or -not $actual.beijing -or $actual.worker -ne {quote_ps(executable)} -or $actual.arguments -ne {quote_ps(arguments)}){{throw 'Task verification failed'}}
 @{{ok=$true;task=$actual;previous_xml=$before}}|ConvertTo-Json -Depth 4 -Compress
}}catch{{
 $restored=$false
 try{{if($before){{$null=$folder.RegisterTask($name,$before,6,$sid,$null,3,$null)}}else{{$folder.DeleteTask($name,0)}};$restored=$true}}catch{{}}
 @{{ok=$false;restored=$restored}}|ConvertTo-Json -Compress
}}
'''
    result=json.loads(ps(script).stdout.strip() or 'null')
    if not result or not result.get('ok'):
        task._snapshot_available=False
        raise UserError('系统计划保存失败，已恢复原任务。' if result and result.get('restored') else '系统计划保存未能确认，请检查任务计划程序和当前用户权限。')
    task._previous_xml=result['previous_xml'];task._snapshot_available=True
    return result['task']


def restore(task):
    from .core import ps,quote_ps,TASK_DESCRIPTION
    if not getattr(task,'_snapshot_available',False):return
    before=task._previous_xml
    command=(f"$null=$folder.RegisterTask($name,{quote_ps(before)},6,$sid,$null,3,$null)" if before else
             f"$t=Find-Task $name;if($t -and $t.Definition.RegistrationInfo.Description -eq {quote_ps(TASK_DESCRIPTION)}){{$folder.DeleteTask($name,0)}}")
    ps(COM+f'\n$name={quote_ps(task.name)};$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;'+command+";Write-Output 'ok'")
