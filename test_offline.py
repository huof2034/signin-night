"""Offline checks for credential protection and sign-in execution safeguards."""
import asyncio
import contextlib
from datetime import datetime
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

import app


class FrozenDate(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 19, 22, 5, tzinfo=app.CHINA)


class SafeguardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='ahut-offline-')
        self.folder = Path(self.temporary.name)
        self.patchers = [patch.object(app, 'DATA', self.folder),
                         patch.object(app, 'ACCOUNT', self.folder / ('test.dpapi' if app.IS_WINDOWS else 'test.json'))]
        for patcher in self.patchers:
            patcher.start()
        self.account = {'student_id': '259099999', 'password_hash': hashlib.md5(b'offline-only').hexdigest()}

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temporary.cleanup()

    def test_disabled_does_not_load_account_or_upstream(self):
        with patch.object(app, 'load_account') as account, patch.object(app, 'load_upstream') as upstream:
            self.assertEqual(app.run(), 0)
            account.assert_not_called()
            upstream.assert_not_called()

    def test_outside_window_does_not_load_account(self):
        class Early(FrozenDate):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 19, 21, 59, tzinfo=app.CHINA)
        app.set_enabled(True)
        with patch.object(app, 'datetime', Early), patch.object(app, 'load_account') as account:
            self.assertEqual(app.run(), 0)
            account.assert_not_called()

    def test_missing_account_never_contacts_upstream(self):
        app.set_enabled(True)
        with patch.object(app, 'datetime', FrozenDate), patch.object(app, 'load_upstream') as upstream:
            with self.assertRaises(ValueError):
                app.run()
            upstream.assert_not_called()

    def test_account_roundtrip_and_no_plaintext_on_windows(self):
        app.save_account(self.account)
        self.assertEqual(app.load_account(), self.account)
        if app.IS_WINDOWS:
            stored = app.ACCOUNT.read_bytes()
            self.assertNotIn(self.account['student_id'].encode(), stored)
            self.assertNotIn(self.account['password_hash'].encode(), stored)
            damaged = bytearray(stored)
            damaged[-1] ^= 1
            with self.assertRaises(OSError):
                app.dpapi(bytes(damaged), decrypt=True)

    def test_same_day_success_skips_network(self):
        app.save_account(self.account)
        app.set_enabled(True)
        app.remember_success('2026-10-19')
        with patch.object(app, 'datetime', FrozenDate), patch.object(app, 'load_upstream') as upstream:
            self.assertEqual(app.run(), 0)
            upstream.assert_not_called()

    def test_success_persists_then_second_run_skips(self):
        app.save_account(self.account)
        app.set_enabled(True)
        with patch.object(app, 'datetime', FrozenDate), patch.object(app, 'load_upstream', return_value=Mock()), \
             patch.object(app, 'setup_logging'), patch.object(app, 'perform', new=AsyncMock(return_value={'success': True})) as perform:
            self.assertEqual(app.run(), 0)
            self.assertEqual(app.last_success(self.account), '2026-10-19')
            self.assertEqual(app.run(), 0)
            self.assertEqual(perform.await_count, 1)

    def test_failed_attempt_does_not_write_success(self):
        app.save_account(self.account)
        app.set_enabled(True)
        with patch.object(app, 'datetime', FrozenDate), patch.object(app, 'load_upstream', return_value=Mock()), \
             patch.object(app, 'setup_logging'), patch.object(app, 'perform', new=AsyncMock(return_value={'success': False})):
            self.assertEqual(app.run(), 1)
            self.assertIsNone(app.last_success(self.account))

    def test_switch_refuses_while_execution_lock_is_held(self):
        app.set_enabled(True)
        with app.exclusive():
            with self.assertRaises(app.BusyError):
                app.set_enabled(False)
        self.assertTrue(app.enabled())

    def test_success_record_does_not_apply_to_different_account(self):
        app.save_account(self.account)
        app.remember_success('2026-10-19')
        second = dict(self.account, student_id='259088888')
        app.save_account(second)
        self.assertIsNone(app.last_success(second))

    def test_upstream_debug_is_off_and_session_is_closed(self):
        async def verify():
            upstream = app.load_upstream()
            self.assertEqual(upstream.USER_LIST, [])
            self.assertEqual(upstream.generate_signCode(1792418400), upstream.generate_signCode(1792418400000))
            upstream.sign_in = AsyncMock(return_value={'success': True})
            result = await app.perform(upstream, self.account)
            user = upstream.sign_in.await_args.args[0]
            self.assertFalse(upstream.sign_in.await_args.kwargs['debug'])
            self.assertTrue(user._session.closed)
            self.assertEqual(user.is_encrypted, 1)
            self.assertTrue(result['success'])
        asyncio.run(verify())


if __name__ == '__main__':
    with contextlib.redirect_stdout(io.StringIO()):
        unittest.main()
