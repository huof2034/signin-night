"""Run login rejection/retry in a fresh GUI process with an isolated fake school."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


def driver():
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    import asyncio
    import hashlib
    import tempfile
    from unittest.mock import Mock, patch
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer, QThread
    from desktop import core, gui
    from test_desktop import Scheduler
    import app as legacy

    class IsolatedService(core.Service):
        async def _verify(self, account):
            await asyncio.sleep(.12)
            if account['password_hash'] == hashlib.md5(b'network-test').hexdigest():
                raise core.UserError('无法完成学校账号验证，请检查网络或稍后重试。')
            if account['password_hash'] != hashlib.md5(b'correct-test').hexdigest():
                raise core.UserError('学号或考勤密码未通过验证，请检查后重试。')
            return '演示账号'

    with tempfile.TemporaryDirectory(prefix='ahut-login-runtime-') as folder, patch.object(core,'execute',return_value=Mock(returncode=0,stdout='',stderr='')), patch.object(core.Service,'_sid',return_value='S-1-5-21-1'), patch.object(legacy,'perform',side_effect=AssertionError('Signing in is forbidden in this check')):
        service=IsolatedService(data=Path(folder)/'data',old_root=Path(folder)/'old',scheduler=Scheduler(),migrate=False)
        service.settings['auto_login']=False; service.save()
        from desktop.appearance import Preferences
        Preferences(service.data).set(startup_animation=False,theme='light')
        legacy.save_account({'student_id':'259099999','password_hash':'a'*32})
        original=legacy.ACCOUNT.read_bytes()
        app=QApplication([]); result={'stage':0,'error':None}
        poll=QTimer(); poll.setInterval(30)
        def tick():
            try:
                window=next((w for w in app.topLevelWidgets() if isinstance(w,gui.Window)),None)
                if not window or window.busy: return
                assert QThread.currentThread()==app.thread()
                assert window.isVisible()
                stage=result['stage']
                if stage in (1,2):
                    assert window.root_stack.currentIndex()==0 and window.login_error.isVisible()
                    assert window.login_button.isEnabled() and legacy.ACCOUNT.read_bytes()==original
                if stage==3:
                    assert window.root_stack.currentIndex()==1 and window.authenticated
                    window.go(1); result['stage']=4; return
                if stage==4:
                    inner=window.time_edit.lineEdit()
                    assert inner.width()>inner.fontMetrics().horizontalAdvance('22:00')+20
                    assert window.time_edit.text()=='22:00'
                    for theme in ('dark','system','wallpaper','light'):
                        window.set_theme(theme)
                        assert window.time_edit.text()=='22:00'
                    window.go(5); assert window.page_heading.text()=='外观与通知'
                    assert window.tray_themes['light'].isChecked()
                    assert not window.transparency_slider.isEnabled()
                    window.set_theme('wallpaper'); window.transparency_slider.setValue(65); window.flush_transparency()
                    assert Preferences(service.data).value['surface_transparency']==65
                    assert window.windowOpacity()==1.0
                    from PySide6.QtGui import QImage,QColor
                    image=QImage(4,4,QImage.Format.Format_RGB32);image.fill(QColor('#203f60'))
                    window.wallpaper_canvas.set_frame(image)
                    assert window.wallpaper_canvas.enabled and window.wallpaper_canvas.frame.width()==4
                    poll.stop(); window.quit_ui(); return
                password=['wrong-test','network-test','correct-test'][stage]
                result['stage']+=1
                window.student_edit.setText('259099999'); window.password_edit.setText(password); window.login_button.click()
            except Exception as exc:
                result['error']=type(exc).__name__; poll.stop(); app.quit()
        poll.timeout.connect(tick); poll.start()
        def timeout():
            result['error']='Timeout'; app.quit()
        watchdog=QTimer(); watchdog.setSingleShot(True); watchdog.timeout.connect(timeout); watchdog.start(12_000)
        gui.run(service)
        diagnostic=(service.data/'ui-diagnostics.log').read_text(encoding='utf-8')
        assert result['error'] is None and result['stage']==4, result
        assert 'callback-error' not in diagnostic and 'ui-exit' in diagnostic
        if sys.stdout:
            print('wrong-password -> network-error -> successful-retry: survived; saved account preserved; no check-in')


class RuntimeLoginTest(unittest.TestCase):
    def test_full_gui_event_loop_survives_rejected_password_and_retry(self):
        result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--driver'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=25)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('successful-retry',result.stdout)


if __name__=='__main__':
    if '--driver' in sys.argv: driver()
    else: unittest.main()
