"""Real Qt event-loop / frozen standard-edition smoke; no school or task writes."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys
from pathlib import Path


def driver():
    import asyncio,hashlib,tempfile
    from unittest.mock import patch,Mock
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer,QTime,QThread
    from desktop import accounts,core,gui
    from desktop.appearance import Preferences
    from test_desktop import Scheduler
    import app as legacy
    class FakeSchool(accounts.StandardService):
        async def _verify(self,account):
            await asyncio.sleep(.12)
            if account['password_hash']!=hashlib.md5(b'correct-test').hexdigest():raise core.UserError('学号或考勤密码未通过验证，请检查后重试。')
            return '离线演示账号'
    with tempfile.TemporaryDirectory(prefix='ahut-standard-runtime-') as folder,patch.object(core,'execute',return_value=Mock(returncode=0,stdout='',stderr='')),patch.object(core.Service,'_sid',return_value='S-1-5-21-1'),patch.object(legacy,'perform',side_effect=AssertionError('No sign-in allowed')):
        tasks={slot:Scheduler() for slot in accounts.SLOTS};service=FakeSchool(data=Path(folder)/'data',migrate=False,scheduler_factory=tasks.get)
        service.login('259099999','correct-test',False);service.resume()
        Preferences(service.data).set(theme='light',startup_animation=False,auto_check_updates=False)
        app=QApplication.instance() or QApplication([]);result={'stage':0,'error':None};poll=QTimer();poll.setInterval(35)
        def tick():
            try:
                w=next((w for w in app.topLevelWidgets() if isinstance(w,gui.Window)),None)
                if not w or w.busy:return
                assert QThread.currentThread()==app.thread();assert w.isVisible()
                stage=result['stage']
                if stage==0:
                    from desktop import updates
                    assert w.title_bar.version.isVisible() and w.title_bar.version.text()=='v'+updates.VERSION
                    w.enter_offline();w.show_login(add=True);w.student_edit.setText('259088888');w.password_edit.setText('wrong-test');result['stage']=1;w.login_button.click()
                elif stage==1:
                    assert w.login_error.isVisible() and len(service.status()['accounts'])==1 and tasks['primary'].enabled
                    w.password_edit.setText('correct-test');result['stage']=2;w.login_button.click()
                elif stage==2:
                    assert w.root_stack.currentIndex()==1 and len(w.state['accounts'])==2 and not w.state['enabled'];assert not w.add_account_button.isEnabled()
                    w.go(1);w.time_edit.setTime(QTime(22,10));result['stage']=3;w.apply_time()
                elif stage==3:
                    assert tasks['secondary'].time=='22:10';result['stage']=4;w.toggle_enabled(True)
                elif stage==4:
                    assert tasks['primary'].enabled and tasks['secondary'].enabled;result['stage']=5;w.account_combo.setCurrentIndex(w.account_combo.findData('primary'))
                elif stage==5:
                    assert w.time_edit.text()=='22:00' and w.state['selected_profile']=='primary';result['stage']=6;w.toggle_enabled(False)
                elif stage==6:
                    assert not tasks['primary'].enabled and tasks['secondary'].enabled
                    for theme in ('dark','system','wallpaper','light'):
                        w.set_theme(theme);assert w.time_edit.text()=='22:00'
                    w.go(4);assert w.page_heading.text()=='账号管理';assert not w.quick_cloud.isEnabled() and not w.detail_cloud.isEnabled()
                    assert w.time_edit.lineEdit().width()>80;assert w.password_edit.text()==''
                    w.time_edit.setCurrentSection(w.time_edit.Section.MinuteSection);w.time_edit.setTime(QTime(22,0));w.time_edit.stepDown();assert w.time_edit.time()==QTime(21,59)
                    assert w.time_edit.minimumTime()==QTime(21,30) and w.time_edit.maximumTime()==QTime(23,30)
                    from desktop import updates
                    fake=updates.Release('1.6.0',updates.REPOSITORY+'/releases/tag/v1.6.0','',True)
                    with patch.object(updates,'check_latest',return_value=fake):
                        result['stage']=7;w.check_update(manual=True);w.update_pool.waitForDone(2000)
                elif stage==7:
                    if w.update_checking:return
                    assert w.update_download.isVisible() and w.tray_download.isVisible() and '1.6.0' in w.update_status.text()
                    assert not w.busy and not tasks['primary'].enabled and tasks['secondary'].enabled
                    w.title_bar.version.click();app.processEvents();assert w.title_bar.menu.isVisible()
                    assert w.title_bar.check_action.isEnabled() and w.title_bar.download_action.isVisible();w.title_bar.menu.hide()
                    w.title_bar.maximize.click();app.processEvents();assert w.isMaximized()
                    w.title_bar.maximize.click();app.processEvents();assert not w.isMaximized()
                    poll.stop();result['stage']=8;w.quit_ui()
            except Exception as exc:result['error']=type(exc).__name__;poll.stop();app.quit()
        poll.timeout.connect(tick);poll.start();watchdog=QTimer();watchdog.setSingleShot(True)
        def timeout():result['error']='Timeout';app.quit()
        watchdog.timeout.connect(timeout);watchdog.start(20_000);gui.run(service)
        assert result=={'stage':8,'error':None},result
        if sys.stdout:print('standard-two-account-runtime: passed; no real school or scheduler access')


if __name__=='__main__':driver()
