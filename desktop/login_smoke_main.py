"""Separate frozen regression executable; never included in the normal app."""
import json
from pathlib import Path
import sys
import traceback
from test_accounts_runtime import driver

result = Path(sys.executable).parent / 'login-smoke-result.json'
try:
    driver()
    import io,unittest
    from test_records import RecordTests
    checks=['test_response_is_saved_before_async_cleanup_and_survives_cleanup_failure','test_receipt_still_works_when_compatibility_file_write_fails','test_recovery_preserves_original_and_marks_provenance_without_network','test_receipt_write_failure_is_explicit_and_does_not_repeat_submission']
    stream=io.StringIO();suite=unittest.TestSuite(RecordTests(name) for name in checks)
    outcome=unittest.TextTestRunner(stream=stream).run(suite)
    if not outcome.wasSuccessful():raise RuntimeError(stream.getvalue())
except BaseException:
    result.write_text(json.dumps({'passed':False,'traceback':traceback.format_exc()},ensure_ascii=False),encoding='utf-8')
    raise SystemExit(1)
result.write_text(json.dumps({'passed':True,'cases':['add_rejected_password','retry_add','no_signin','preserve_first_plan','second_defaults_paused','account_limit','independent_times','independent_enabling','picker','independent_pause','visible_time','four_themes','account_management','vps_disabled','main_thread_callbacks','password_cleared','minute_carry','time_bounds','async_update_check','update_preserves_plans','caption_on_login','caption_version_menu','caption_update_state','caption_window_controls','success_receipt_before_cleanup','receipt_survives_compat_file_failure','evidence_recovery','no_duplicate_after_record_error']}),encoding='utf-8')
