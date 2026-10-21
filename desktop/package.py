"""Package only the frozen application; runtime credentials stay outside it."""
from pathlib import Path
import hashlib
import shutil
import zipfile

root = Path(__file__).resolve().parents[1]
application = root / 'dist' / '晚安助手'
executable = application / '晚安助手.exe'
if not executable.is_file():
    raise SystemExit('Build the desktop application first.')
for item in application.rglob('*'):
    if item.name in {'.local', 'account.dpapi', 'account-secondary.dpapi', 'profiles.json', 'last-success.json', 'last-success-secondary.json', 'receipt-primary.json', 'receipt-secondary.json', 'last-success-primary.before-recovery.json', 'last-success-secondary.before-recovery.json', 'account.json', 'id_ed25519', 'vps.json', 'signin.log', 'signin-primary.log', 'signin-secondary.log', 'desktop.json', 'ui-preferences.json', 'events.jsonl', 'icuuc.dll', 'icudt78.dll'}:
        raise SystemExit('Refusing to package runtime data.')
shutil.copyfile(root / 'docs' / '使用说明.md', application / '使用说明.md')
shutil.copyfile(root / 'THIRD_PARTY_NOTICES.md', application / 'THIRD_PARTY_NOTICES.md')
shutil.copytree(root / 'desktop' / 'licenses', application / '_internal' / 'third-party-licenses' / 'Qt', dirs_exist_ok=True)
print('Clean application payload prepared for installer.')
