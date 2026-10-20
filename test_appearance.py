"""Offline appearance, wallpaper and notification regressions. No school calls."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import json
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTime, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from desktop import appearance as a, core, gui
from desktop.notifications import EventNotifications
from test_desktop import Scheduler
import app as legacy


class AppearanceDataTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ahut-appearance-'); self.root=Path(self.temp.name)
        self.running=patch.object(a,'engine_running',return_value=True); self.running.start()
    def tearDown(self): self.running.stop(); self.temp.cleanup()

    def test_preferences_default_and_roundtrip_are_separate_from_schedule(self):
        plan=self.root/'desktop.json'; plan.write_text('{"time":"22:00"}')
        prefs=a.Preferences(self.root); self.assertEqual(prefs.value['theme'],'wallpaper')
        prefs.set(theme='dark',startup_animation=False)
        self.assertEqual(a.Preferences(self.root).value['theme'],'dark')
        self.assertEqual(plan.read_text(),'{"time":"22:00"}')
        self.assertEqual(list(self.root.glob('*.tmp')),[])

    def test_corrupt_or_unknown_preferences_fall_back(self):
        path=self.root/'ui-preferences.json'; path.write_text('[]')
        self.assertEqual(a.Preferences(self.root).value,a.DEFAULTS)
        path.write_text('{"theme":"unknown","accent":"url(x)","notifications":"true"}')
        prefs=a.Preferences(self.root); self.assertEqual(prefs.value['theme'],'wallpaper')
        self.assertEqual(prefs.value['accent'],'#3478ed'); self.assertIs(prefs.value['notifications'],True)

    def test_transparency_defaults_and_invalid_values_preserve_old_preferences(self):
        path=self.root/'ui-preferences.json'
        for invalid in [None,-1,101,True,'40',12.5]:
            path.write_text(json.dumps({'theme':'dark','surface_transparency':invalid}),encoding='utf-8')
            prefs=a.Preferences(self.root)
            self.assertEqual(prefs.value['surface_transparency'],14); self.assertEqual(prefs.value['theme'],'dark')
        for valid in [0,14,100]:
            prefs.set(surface_transparency=valid)
            self.assertEqual(a.Preferences(self.root).value['surface_transparency'],valid)

    def test_transparency_styles_only_change_wallpaper_surfaces(self):
        p=a.palette('wallpaper','#226677',True)
        for value,alpha in [(0,255),(14,219),(100,0)]:
            style=a.stylesheet(gui.STYLES,p,'wallpaper',value)
            rgb=QColor(p['surface']).getRgb()[:3]; color=f'rgba({rgb[0]},{rgb[1]},{rgb[2]},{alpha})'
            self.assertIn('QFrame#Card { background:'+color,style)
            self.assertIn('QWidget#Sidebar { background:'+color,style)
        for mode in ('light','dark','system'):
            p=a.palette(mode)
            self.assertEqual(a.stylesheet(gui.STYLES,p,mode,0),a.stylesheet(gui.STYLES,p,mode,100))

    def test_every_theme_has_readable_filled_buttons_and_body(self):
        for mode in a.THEMES:
            for color in ['#ffee22','#080d0e','#ff44ff','#888888']:
                p=a.palette(mode,color,True)
                self.assertGreater((1.05)/(a.luminance(p['accent'])+.05),4.5)
                light,dark=sorted([a.luminance(p['text']),a.luminance(p['surface'])])
                self.assertGreater((dark+.05)/(light+.05),7)

    def setup_wallpaper(self):
        engine=self.root/'engine'; engine.mkdir(); folder=self.root/'current'; folder.mkdir()
        file=folder/'scene.pkg'; file.write_bytes(b'not executed')
        image=QImage(80,50,QImage.Format.Format_RGB32); image.fill(QColor('#138c85')); image.save(str(folder/'preview.png'))
        (folder/'project.json').write_text(json.dumps({'preview':'preview.png'}))
        config={'test-user':{'general':{'wallpaperconfig':{'selectedwallpapers':{'Monitor0':{'file':str(file)}}}},'wproperties':{}}}
        (engine/'config.json').write_text(json.dumps(config)); return engine,folder,config

    def test_engine_current_preview_is_read_only_and_cached(self):
        engine,folder,config=self.setup_wallpaper(); before=(engine/'config.json').read_bytes()
        with patch.object(a,'engine_roots',return_value=[engine]),patch.object(a,'windows_wallpaper',return_value=None):
            reader=a.WallpaperReader(); result=reader.resolve(); self.assertIn('Wallpaper Engine',result['source'])
            self.assertTrue(result['dark']); self.assertIn('预览',result['source'])
            with patch.object(a,'sample_image',side_effect=AssertionError('unchanged preview decoded again')):
                self.assertEqual(reader.resolve(),result)
        self.assertEqual((engine/'config.json').read_bytes(),before)
        self.assertEqual(sorted(p.name for p in folder.iterdir()),['preview.png','project.json','scene.pkg'])

    def test_saved_scheme_color_takes_priority_over_preview(self):
        engine,folder,config=self.setup_wallpaper(); profile=config['test-user']
        profile['wproperties'][str(folder/'scene.pkg')]={'Monitor0':{'schemecolor':'1 0 0'}}
        (engine/'config.json').write_text(json.dumps(config))
        with patch.object(a,'engine_roots',return_value=[engine]): self.assertEqual(a.WallpaperReader().resolve()['accent'],'#ff0000')

    def test_broken_engine_falls_back_to_static_wallpaper(self):
        engine,folder,config=self.setup_wallpaper(); (engine/'config.json').write_text('{broken')
        with patch.object(a,'engine_roots',return_value=[engine]),patch.object(a,'windows_wallpaper',return_value=folder/'preview.png'):
            self.assertIn('Windows',a.WallpaperReader().resolve()['source'])

    def test_stopped_engine_uses_current_windows_wallpaper(self):
        engine,folder,config=self.setup_wallpaper()
        with patch.object(a,'engine_running',return_value=False),patch.object(a,'engine_roots',side_effect=AssertionError('stale WE config must not be read')),patch.object(a,'windows_wallpaper',return_value=folder/'preview.png'):
            self.assertIn('Windows',a.WallpaperReader().resolve()['source'])

    def test_preview_traversal_is_not_read(self):
        engine,folder,config=self.setup_wallpaper()
        (folder/'project.json').write_text(json.dumps({'preview':'../outside.png'}))
        with patch.object(a,'engine_roots',return_value=[engine]),patch.object(a,'windows_wallpaper',return_value=None),patch.object(a,'sample_image',return_value=None) as sample:
            self.assertNotIn('accent',a.WallpaperReader().resolve())
            self.assertTrue(all(call.args[0] is None for call in sample.call_args_list))

    def test_missing_preview_and_network_paths_do_not_trigger_fetches(self):
        self.assertIsNone(a.local_path('https://example.com/image.png'))
        self.assertIsNone(a.local_path(r'\\server\private\wallpaper.png'))
        self.assertIsNone(a.sample_image(self.root/'missing.jpg'))
        with patch.object(a,'engine_roots',return_value=[]),patch.object(a,'windows_wallpaper',return_value=None):
            self.assertNotIn('accent',a.WallpaperReader().resolve())

    def test_old_history_is_ignored_and_new_notifications_are_deduplicated(self):
        started=core.now(); observer=EventNotifications(started)
        event=lambda when,kind:dict(at=when.isoformat(),kind=kind,message='private details never displayed',mode='local')
        old=event(started-timedelta(minutes=1),'success'); fresh=event(started+timedelta(seconds=1),'success')
        self.assertEqual(observer.consume([old],a.DEFAULTS),[])
        result=observer.consume([fresh,old],a.DEFAULTS); self.assertEqual(len(result),1); self.assertNotIn('private',str(result))
        self.assertEqual(observer.consume([fresh],a.DEFAULTS),[])

    def test_disabled_notifications_do_not_replay_when_reenabled(self):
        started=core.now(); observer=EventNotifications(started)
        event=dict(at=(started+timedelta(seconds=1)).isoformat(),kind='failed')
        self.assertEqual(observer.consume([event],{**a.DEFAULTS,'notifications':False}),[])
        self.assertEqual(observer.consume([event],a.DEFAULTS),[])

    def test_cloud_failure_and_mode_preferences(self):
        observer=EventNotifications(core.now()-timedelta(seconds=1))
        events=[dict(at=core.now().isoformat(),kind='failed'),dict(at=core.now().isoformat(),kind='mode',mode='cloud')]
        messages=observer.consume(events,{**a.DEFAULTS,'notify_mode':False},'cloud')
        self.assertEqual(len(messages),1); self.assertIn('VPS',messages[0][1]); self.assertTrue(messages[0][2])


class AppearanceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([]); cls.app.setStyle('Fusion')
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ahut-theme-qt-'); self.root=Path(self.temp.name)
        self.previous=(legacy.DATA,legacy.ACCOUNT,legacy.ROOT)
        self.exec_patch=patch.object(core,'execute',return_value=Mock(returncode=0,stdout='',stderr='')); self.exec_patch.start()
        self.sid_patch=patch.object(core.Service,'_sid',return_value='S-1-5-21-1'); self.sid_patch.start()
        self.reader_patch=patch.object(a.WallpaperReader,'resolve',return_value={'source':'test','accent':'#226677','dark':True}); self.reader_patch.start()
        self.service=core.Service(data=self.root/'data',old_root=self.root/'old',scheduler=Scheduler(),migrate=False)
        self.service.settings.update(auto_login=False,managed=True); self.service.save()
        self.window=gui.Window(self.service); self.window.show(); self.app.processEvents()
    def tearDown(self):
        self.window._quitting=True
        for timer in self.window.findChildren(gui.QTimer): timer.stop()
        self.window.pool.waitForDone(3000); self.window.appearance_pool.waitForDone(3000); self.app.processEvents()
        self.window.tray.hide(); self.window.close(); self.window.deleteLater(); self.app.processEvents()
        self.exec_patch.stop(); self.sid_patch.stop(); self.reader_patch.stop()
        legacy.DATA,legacy.ACCOUNT,legacy.ROOT=self.previous; self.temp.cleanup()

    def test_all_themes_preserve_visible_time_and_unsaved_changes(self):
        self.window.enter_offline(); self.window.go(1); self.window.time_edit.setTime(QTime(22,10))
        before=(self.service.data/'desktop.json').read_bytes()
        for theme in a.THEMES:
            self.window.set_theme(theme); self.app.processEvents()
            inner=self.window.time_edit.lineEdit()
            self.assertGreater(inner.width(),inner.fontMetrics().horizontalAdvance('22:10')+20)
            self.assertEqual(self.window.time_edit.text(),'22:10')
            self.assertTrue(all(c.currentData()==theme for c in self.window.theme_combos))
            self.assertEqual((self.service.data/'desktop.json').read_bytes(),before)

    def test_system_changes_only_apply_to_system_theme(self):
        with patch('desktop.appearance.system_dark',return_value=True):
            self.window.set_theme('system'); self.assertTrue(self.window.theme_colors['dark'])
        with patch('desktop.appearance.system_dark',return_value=False):
            self.window.system_theme_changed(); self.assertFalse(self.window.theme_colors['dark'])
            self.window.set_theme('dark'); self.window.system_theme_changed(); self.assertTrue(self.window.theme_colors['dark'])

    def test_transparency_previews_saves_and_resets_without_affecting_schedule(self):
        w=self.window; w.enter_offline(); w.go(5); w.set_theme('wallpaper')
        schedule=(self.service.data/'desktop.json').read_bytes()
        w.transparency_slider.setValue(72)
        QTest.qWait(150)
        self.assertEqual(w.transparency_value.text(),'72%')
        self.assertEqual(w.windowOpacity(),1.0)
        self.assertIn(',71)',self.app.styleSheet())
        QTest.qWait(350)
        self.assertEqual(a.Preferences(self.service.data).value['surface_transparency'],72)
        w.set_theme('dark'); self.assertFalse(w.transparency_slider.isEnabled()); self.assertFalse(w.transparency_reset.isEnabled())
        w.set_theme('wallpaper'); self.assertTrue(w.transparency_slider.isEnabled()); self.assertEqual(w.transparency_slider.value(),72)
        w.transparency_reset.click(); self.assertEqual(a.Preferences(self.service.data).value['surface_transparency'],14)
        self.assertEqual((self.service.data/'desktop.json').read_bytes(),schedule)
        self.assertIsNone(w.account_badge.graphicsEffect())

    def test_transparency_disk_failure_restores_saved_value(self):
        w=self.window; w.enter_offline(); w.go(5)
        w.transparency_slider.setValue(100)
        with patch.object(w.preferences,'set',side_effect=OSError('test write failure')):
            w.flush_transparency()
        self.assertEqual(w.transparency_slider.value(),14)
        self.assertIn('未能保存',w.notice.text()); self.assertEqual(w.windowOpacity(),1.0)

    def test_tray_status_resume_and_theme_selection(self):
        self.window.tray_themes['dark'].trigger(); self.assertEqual(self.window.preferences.value['theme'],'dark')
        self.service.settings['enabled']=False; self.service.save(); self.window.refresh()
        self.assertEqual(self.window.tray_pause.text(),'恢复自动签到')
        self.assertIn('22:00',self.window.tray_status.text())

    def test_toast_and_master_toggle_are_consistent_with_settings(self):
        with patch.object(self.window.tray,'isVisible',return_value=True),patch.object(self.window.tray,'showMessage') as toast:
            self.window.test_notification(); self.assertEqual(toast.call_count,1)
            self.window.set_notification_preference(False); self.window.test_notification(); self.assertEqual(toast.call_count,1)
            self.assertFalse(self.window.preference_checks['notifications'].isChecked())

    def test_close_to_tray_and_full_exit_option(self):
        with patch.object(self.window.tray,'isVisible',return_value=True):
            self.window.close(); self.assertFalse(self.window.isVisible()); self.assertFalse(self.window._quitting)
            self.window.restore(); self.window.save_preference('close_to_tray',False)
            with patch.object(self.window,'quit_ui') as quit_ui: self.window.close(); quit_ui.assert_called_once()

    def test_startup_animation_finishes_and_can_be_disabled(self):
        self.window.save_preference('startup_animation',False); self.window.play_startup()
        self.assertFalse(self.window.findChildren(gui.StartupOverlay))
        self.window.save_preference('startup_animation',True); self.window.play_startup()
        self.assertTrue(self.window.findChildren(gui.StartupOverlay))
        for _ in range(40):
            QTest.qWait(50); QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            if not self.window.findChildren(gui.StartupOverlay): break
        self.assertFalse(self.window.findChildren(gui.StartupOverlay))


if __name__=='__main__': unittest.main()
