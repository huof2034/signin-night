from pathlib import Path
SMOKE_LOGIN = True
exec(compile((Path(SPECPATH) / 'app.spec').read_text(encoding='utf-8'), 'app.spec', 'exec'))
