"""Release checks and asynchronous UI, without network or attendance calls."""
import io
import json
from unittest import TestCase, main
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from PySide6.QtTest import QTest
from desktop import updates
import test_accounts_ui as fixtures


def release(version='1.6.0'):
    name=f'AHUTSignIn-Setup-{version}-x64.exe'
    return dict(tag_name='v'+version,html_url=updates.REPOSITORY+'/releases/tag/v'+version,
        draft=False,prerelease=False,assets=[dict(name=name,state='uploaded',size=100,
        browser_download_url=updates.REPOSITORY+'/releases/download/v'+version+'/'+name)])


class ReleaseTests(TestCase):
    def test_numeric_comparison_and_current_version(self):
        self.assertTrue(updates.parse_release(release('1.10.0'),'1.9.0').available)
        self.assertFalse(updates.parse_release(release('1.5.0')).available)
        self.assertFalse(updates.parse_release(release('1.4.0')).available)

    def test_rejects_untrusted_urls_and_incomplete_installers(self):
        for field,value in [('draft',True),('prerelease',True),('html_url','https://example.com'),('assets',[])]:
            item=release();item[field]=value
            with self.subTest(field=field), self.assertRaises(updates.UpdateError):updates.parse_release(item)
        item=release();item['assets'][0]['browser_download_url']='https://example.com/install.exe'
        with self.assertRaises(updates.UpdateError):updates.parse_release(item)

    def test_rejects_invalid_tags(self):
        for tag in ('v1.6.0-rc1','latest','v01.6.0','v1.6',None):
            item=release();item['tag_name']=tag
            with self.subTest(tag=tag), self.assertRaises(updates.UpdateError):updates.parse_release(item)

    def test_public_request_contains_no_account_or_authorization(self):
        with patch.object(updates,'urlopen',return_value=io.BytesIO(json.dumps(release()).encode())) as call:
            self.assertTrue(updates.check_latest().available)
        request=call.call_args.args[0]
        self.assertEqual(request.full_url,updates.API);self.assertIsNone(request.data)
        self.assertNotIn('Authorization',request.headers);self.assertEqual(call.call_args.kwargs['timeout'],10)

    def test_network_errors_and_rate_limits_are_explained(self):
        for error,expected in [(URLError('offline'),'无法连接'),(HTTPError(updates.API,403,'rate',{},None),'频率')]:
            with patch.object(updates,'urlopen',side_effect=error),self.assertRaisesRegex(updates.UpdateError,expected):updates.check_latest()

    def test_limits_response_size_and_rejects_invalid_json(self):
        for value in (b'x'*(updates.MAX_BYTES+1),b'bad-json'):
            with patch.object(updates,'urlopen',return_value=io.BytesIO(value)),self.assertRaises(updates.UpdateError):updates.check_latest()


class UpdateUiTests(TestCase):
    setUpClass=classmethod(fixtures.StandardUiTests.setUpClass.__func__)
    setUp=fixtures.StandardUiTests.setUp
    tearDown=fixtures.StandardUiTests.tearDown

    def wait_update(self):
        for _ in range(150):
            self.app.processEvents()
            if not self.window.update_checking:return
            QTest.qWait(10)
        self.fail('Update check did not finish')

    def test_manual_check_works_when_auto_disabled_and_exposes_safe_download(self):
        w=self.window;w.preferences.set(auto_check_updates=False)
        with patch.object(updates,'check_latest',return_value=updates.parse_release(release())) as check:
            w.auto_check_update();check.assert_not_called()
            w.check_update(manual=True);self.wait_update();check.assert_called_once()
        self.assertFalse(w.busy);self.assertTrue(w.tray_download.isVisible())
        self.assertIn('1.6.0',w.update_status.text());self.assertTrue(w.update_button.isEnabled())
        with patch('PySide6.QtGui.QDesktopServices.openUrl') as open_url:w.open_update()
        self.assertEqual(open_url.call_args.args[0].toString(),release()['html_url'])

    def test_auto_check_error_is_quiet_and_does_not_change_plan(self):
        w=self.window;before=self.service.store();notice=w.notice.text()
        w.preferences.set(auto_check_updates=True)
        with patch.object(updates,'check_latest',side_effect=updates.UpdateError('无法连接 GitHub')):
            w.auto_check_update();self.wait_update()
        self.assertEqual(self.service.store(),before);self.assertEqual(w.notice.text(),notice)
        self.assertIn('无法连接',w.update_status.text());self.assertEqual(w.configuration_error,'')

    def test_auto_schedule_and_preferences_persist(self):
        from desktop.appearance import Preferences
        w=self.window;self.assertEqual(w.update_timer.interval(),4*60*60*1000)
        self.assertEqual(w.update_start_timer.interval(),8000)
        w.save_preference('auto_check_updates',False)
        self.assertFalse(Preferences(self.service.data).value['auto_check_updates'])


if __name__=='__main__':main()
