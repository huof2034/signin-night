"""Separate frozen regression executable; never included in the normal app."""
import json
from pathlib import Path
import sys
import traceback
from test_accounts_runtime import driver

result = Path(sys.executable).parent / 'login-smoke-result.json'
try:
    driver()
except BaseException:
    result.write_text(json.dumps({'passed':False,'traceback':traceback.format_exc()},ensure_ascii=False),encoding='utf-8')
    raise SystemExit(1)
result.write_text(json.dumps({'passed':True,'cases':['add_rejected_password','retry_add','no_signin','preserve_first_plan','second_defaults_paused','account_limit','independent_times','independent_enabling','picker','independent_pause','visible_time','four_themes','account_management','vps_disabled','main_thread_callbacks','password_cleared','minute_carry','time_bounds','async_update_check','update_preserves_plans','caption_on_login','caption_version_menu','caption_update_state','caption_window_controls']}),encoding='utf-8')
