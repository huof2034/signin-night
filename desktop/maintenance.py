"""Installer lifecycle. Never submit attendance or delete saved credentials."""
import argparse
import contextlib
import json
from pathlib import Path
import sys
from . import core


def uninstall_tasks(executable):
    expected=core.quote_ps(str(Path(executable).resolve()))
    core.ps(f"""
foreach($name in @({core.quote_ps(core.TASK)},{core.quote_ps(core.TASK+'-Secondary')})){{
 $t=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
 if($t -and $t.Description -eq {core.quote_ps(core.TASK_DESCRIPTION)} -and $t.Actions.Count -gt 0 -and @($t.Actions | Where-Object {{$_.Execute -ne {expected}}}).Count -eq 0){{
  Unregister-ScheduledTask -TaskName $name -Confirm:$false
 }}
}}
Write-Output 'ok'
""")


def install_tasks(data=None):
    from .accounts import StandardService
    service=StandardService(data=data,migrate=not data)
    with contextlib.ExitStack() as stack:
        for slot in ('primary','secondary'):stack.enter_context(core.external_lock(service.data/'locks'/slot))
        stack.enter_context(core.external_lock(service.data/'profiles-store'))
        for slot,profile in service.store()['profiles'].items():
            if profile['managed']:
                service.account(slot)
                service.schedulers[slot].apply(profile['time'],profile['enabled'])


def main(argv=None):
    parser=argparse.ArgumentParser()
    for flag in ('install-tasks','uninstall-tasks','prepare-update'):parser.add_argument('--'+flag,action='store_true')
    parser.add_argument('--self-check');parser.add_argument('--data-dir')
    args=parser.parse_args(argv)
    try:
        if args.self_check:
            import platform
            from PySide6.QtCore import qVersion
            from PySide6.QtGui import QImage
            from .live_wallpaper import HERE,VENDOR
            report={'python':platform.python_version(),'qt':qVersion(),'architecture':platform.machine(),
                'image':not QImage(2,2,QImage.Format.Format_RGB32).isNull(),
                'wallpaper_components':all(p.is_file() for p in [VENDOR/'wallpaper-api/node.exe',VENDOR/'capture/windows_capture.pyd',VENDOR/'repkg/RePKG.exe',HERE/'wallpaper_bridge.cjs'])}
            import importlib.util
            capture=importlib.util.spec_from_file_location('windows_capture',VENDOR/'capture/windows_capture.pyd')
            module=importlib.util.module_from_spec(capture);capture.loader.exec_module(module)
            report['capture_import']=True
            report['node']=core.execute([str(VENDOR/'wallpaper-api/node.exe'),'--version'],timeout=10).stdout.strip()
            report['school_module']=callable(core.legacy.load_upstream().sign_in)
            report['ok']=all(report[k] for k in ('image','wallpaper_components','school_module','capture_import','node'))
            Path(args.self_check).write_text(json.dumps(report),encoding='utf-8')
            return 0 if report['ok'] else 1
        if args.prepare_update:
            import os
            core.ps(f"if(Get-CimInstance Win32_Process | Where-Object {{$_.ExecutablePath -eq {core.quote_ps(sys.executable)} -and $_.ProcessId -ne {os.getpid()}}}){{throw 'Application is running'}}")
        elif args.uninstall_tasks:uninstall_tasks(sys.executable)
        elif args.install_tasks:install_tasks(args.data_dir)
        else:return 1
        return 0
    except Exception:
        return 1
