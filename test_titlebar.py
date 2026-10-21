"""Clickable caption version and window controls, with synthetic accounts."""
from unittest import TestCase,main
from unittest.mock import patch
from PySide6.QtCore import QPoint,Qt
from PySide6.QtTest import QTest
from desktop import updates
from desktop.window_chrome import resize_hit
import test_accounts_ui as fixtures


class TitleBarTests(TestCase):
    setUpClass=classmethod(fixtures.StandardUiTests.setUpClass.__func__)
    setUp=fixtures.StandardUiTests.setUp
    tearDown=fixtures.StandardUiTests.tearDown

    def test_version_menu_on_login_and_main_screens(self):
        w=self.window;bar=w.title_bar
        self.assertEqual(bar.version.text(),'v'+updates.VERSION)
        for screen in (0,1):
            w.root_stack.setCurrentIndex(screen);self.app.processEvents()
            self.assertTrue(bar.version.isVisible())
            QTest.mouseClick(bar.version,Qt.MouseButton.LeftButton);self.app.processEvents()
            self.assertTrue(bar.menu.isVisible());self.assertEqual(bar.check_action.text(),'检查更新');bar.menu.hide()

    def test_version_menu_calls_existing_manual_check(self):
        w=self.window
        with patch.object(w,'check_update') as check:w.title_bar.check_action.trigger()
        check.assert_called_once_with(manual=True)
        w.update_checking=True;w.title_bar.sync()
        self.assertFalse(w.title_bar.check_action.isEnabled());self.assertIn('正在检查',w.title_bar.check_action.text())
        w.update_checking=False;w.title_bar.sync();self.assertTrue(w.title_bar.check_action.isEnabled())

    def test_title_drag_excludes_version_and_window_buttons(self):
        w=self.window;bar=w.title_bar
        self.assertTrue(bar.drag_at(bar.mapTo(w,QPoint(20,22))))
        for control in (bar.version,bar.minimize,bar.maximize,bar.close_button):
            self.assertFalse(bar.drag_at(control.mapTo(w,control.rect().center())))
        self.assertFalse(bar.drag_at(QPoint(20,100)))

    def test_caption_controls_and_double_click_toggle_maximize(self):
        w=self.window;bar=w.title_bar
        QTest.mouseClick(bar.maximize,Qt.MouseButton.LeftButton);self.app.processEvents();self.assertTrue(w.isMaximized())
        self.assertEqual(bar.maximize.toolTip(),'还原')
        QTest.mouseDClick(bar,Qt.MouseButton.LeftButton,pos=QPoint(20,22));self.app.processEvents();self.assertFalse(w.isMaximized())
        bar.minimize.click()
        self.app.processEvents();self.assertTrue(w.isMinimized());w.showNormal();self.app.processEvents()
        with patch.object(w.tray,'isVisible',return_value=True),patch.object(w,'closeEvent',wraps=w.closeEvent) as close:
            bar.close_button.click();self.app.processEvents();close.assert_called_once()
        self.assertFalse(w._quitting);self.assertFalse(w.isVisible())

    def test_new_version_menu_download_and_themes(self):
        w=self.window;bar=w.title_bar
        w.update_release=updates.Release('1.6.0',updates.REPOSITORY+'/releases/tag/v1.6.0','',True)
        for mode in ('light','dark','system','wallpaper'):
            w.set_theme(mode);bar.sync();self.app.processEvents()
            self.assertTrue(bar.download_action.isVisible());self.assertIn('1.6.0',bar.download_action.text())
            self.assertEqual(bar.version.text(),'v'+updates.VERSION)
        with patch.object(w,'open_update') as open_update:
            bar.download_action.trigger();open_update.assert_called_once()


class FrameHitTests(TestCase):
    def test_caption_version_matches_windows_resources_and_installer(self):
        from pathlib import Path
        root=Path(__file__).resolve().parent
        self.assertIn("'FileVersion','"+updates.VERSION+"'",(root/'desktop/version.txt').read_text('utf-8'))
        self.assertIn('!define VERSION "'+updates.VERSION+'"',(root/'desktop/installer.nsi').read_text('utf-8-sig'))
        self.assertIn('AHUTSignIn-Setup-'+updates.VERSION+'-x64.exe',(root/'desktop/build-installer.ps1').read_text('utf-8'))

    def test_resize_edges_corners_and_dpi_scaled_border(self):
        for x,y,expected in ((1,1,13),(999,1,14),(1,699,16),(999,699,17),(500,1,12),(500,699,15),(1,300,10),(999,300,11)):
            with self.subTest(x=x,y=y):self.assertEqual(resize_hit(1000,700,x,y,6),expected)
        self.assertIsNone(resize_hit(1000,700,500,300,6))
        self.assertEqual(resize_hit(2000,1400,10,600,12),10)
        self.assertIsNone(resize_hit(1000,700,1,1,6,maximized=True))
        self.assertIsNone(resize_hit(1000,700,-1,20,6))


if __name__=='__main__':main()
