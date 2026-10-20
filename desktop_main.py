"""Single entry point for the desktop UI and its scheduled worker."""
import sys

if __name__ == '__main__':
    if any(flag in sys.argv for flag in ('--install-tasks','--uninstall-tasks','--self-check','--prepare-update')):
        from desktop.maintenance import main
        raise SystemExit(main())
    if '--wallpaper-worker' in sys.argv:
        from desktop.live_wallpaper import worker_main
        raise SystemExit(worker_main(sys.argv[sys.argv.index('--wallpaper-worker')+1:]))
    if '--scheduled' in sys.argv or '--rpc' in sys.argv or '--verify-login' in sys.argv:
        from desktop.core import command_main
        raise SystemExit(command_main())
    try:
        from desktop.gui import run
        if '--data-dir' in sys.argv:
            from desktop.accounts import StandardService
            raise SystemExit(run(StandardService(data=sys.argv[sys.argv.index('--data-dir')+1],migrate=False)))
        raise SystemExit(run())
    except Exception:
        import os
        from pathlib import Path
        import traceback
        folder=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'AHUTSignIn'
        folder.mkdir(exist_ok=True)
        (folder/'startup-error.log').write_text(traceback.format_exc(),encoding='utf-8')
        raise
