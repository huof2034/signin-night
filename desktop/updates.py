"""Official release discovery, verified downloads and updater hand-off."""
from __future__ import annotations

from dataclasses import dataclass
import json
import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, build_opener
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

VERSION = '1.5.4'
REPOSITORY = 'https://github.com/huof2034/signin-night'
API = 'https://api.github.com/repos/huof2034/signin-night/releases/latest'
MAX_BYTES = 512_000


class UpdateError(ValueError):
    pass


def version_tuple(value):
    match = re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value or '')
    if not match:
        raise UpdateError('版本信息格式不正确，请稍后重试。')
    return tuple(map(int, match.groups()))


@dataclass(frozen=True)
class Release:
    version: str
    page: str
    installer: str
    available: bool
    sha256: str = ""
    size: int = 0


def parse_release(value, current=VERSION):
    if not isinstance(value, dict) or value.get('draft') or value.get('prerelease'):
        raise UpdateError('暂未获取到正式发布版，请稍后重试。')
    tag = value.get('tag_name')
    if not isinstance(tag, str):
        raise UpdateError('版本信息不完整，请稍后重试。')
    latest = version_tuple(tag)
    version = '.'.join(map(str, latest))
    page = f'{REPOSITORY}/releases/tag/v{version}'
    # Construct trusted URLs ourselves; never open arbitrary release API links.
    if value.get('html_url') != page:
        raise UpdateError('发布地址校验未通过，请从项目主页检查版本。')
    name = f'AHUTSignIn-Setup-{version}-x64.exe'
    installer = f'{REPOSITORY}/releases/download/v{version}/{name}'
    assets = value.get('assets')
    asset=next((a for a in assets if isinstance(a,dict) and a.get('name')==name
        and a.get('browser_download_url')==installer and type(a.get('size')) is int
        and 0<a['size']<=500_000_000 and a.get('state')=='uploaded'),None) if isinstance(assets,list) else None
    if not asset:
        raise UpdateError('新版 Windows 安装包尚未就绪，请稍后重试。')
    digest=asset.get('digest') or ''
    digest=digest[7:] if re.fullmatch(r'sha256:[0-9a-f]{64}',digest) else ''
    return Release(version, page, installer, latest > version_tuple(current),digest,asset['size'])


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url=urlparse(newurl)
        allowed=('github.com','release-assets.githubusercontent.com','objects.githubusercontent.com')
        if url.scheme!='https' or url.hostname not in allowed or url.username or url.password:
            raise UpdateError('下载地址校验失败。')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def download_installer(release, progress=lambda value:None):
    """Download only the selected official release and verify GitHub's SHA-256."""
    version_tuple(release.version)
    expected=f'{REPOSITORY}/releases/download/v{release.version}/AHUTSignIn-Setup-{release.version}-x64.exe'
    if (not release.available or release.installer!=expected or
        not re.fullmatch(r'[0-9a-f]{64}',release.sha256) or not 0<release.size<=500_000_000):
        raise UpdateError('缺少可验证的安装包摘要，请稍后重试。')
    folder=Path(tempfile.mkdtemp(prefix='ahut-update-'))
    target=folder/('AHUTSignIn-Setup-'+release.version+'-x64.exe')
    digest=hashlib.sha256(); total=0
    try:
        req=Request(expected,headers={'User-Agent':'AHUTSignIn/'+VERSION})
        with build_opener(SafeRedirect()).open(req,timeout=30) as response, target.open('xb') as output:
            while True:
                chunk=response.read(1024*256)
                if not chunk: break
                total+=len(chunk)
                if total>release.size:raise UpdateError('下载文件大小不符。')
                digest.update(chunk);output.write(chunk);progress(total*100//release.size)
            output.flush();os.fsync(output.fileno())
        if total!=release.size or digest.hexdigest()!=release.sha256:
            raise UpdateError('安装包校验失败，请重试。')
        return target
    except Exception as exc:
        target.unlink(missing_ok=True)
        folder.rmdir()
        if isinstance(exc,UpdateError):raise
        raise UpdateError('下载安装包失败，请检查网络后重试。') from None



def check_latest(current=VERSION):
    request = Request(API, headers={'Accept': 'application/vnd.github+json',
        'User-Agent': 'AHUTSignIn/' + VERSION, 'X-GitHub-Api-Version': '2022-11-28'})
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise UpdateError('版本信息过大，请稍后重试。')
        value = json.loads(raw)
    except HTTPError as exc:
        if exc.code in (403, 429):
            raise UpdateError('GitHub 暂时限制了检查频率，请稍后重试。') from None
        if exc.code == 404:
            raise UpdateError('暂未找到正式发布版，请稍后重试。') from None
        raise UpdateError('GitHub 暂时不可用，请稍后重试。') from None
    except (URLError, TimeoutError, OSError):
        raise UpdateError('无法连接 GitHub，请检查网络后重试；定时签到不受影响。') from None
    except (ValueError, UnicodeError):
        raise UpdateError('版本信息读取失败，请稍后重试。') from None
    return parse_release(value, current)


def start_installer(installer, release, data, wallpaper_pid=None):
    """Run the bundled native updater from its own temporary directory."""
    import shutil
    import subprocess
    import sys
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        raise UpdateError('请从 Windows 完整程序运行更新。')
    executable = Path(sys.executable).resolve()
    source = Path(__file__).resolve().parent / 'AHUTUpdater.exe'
    installer = Path(installer).resolve()
    work = installer.parent
    if (not source.is_file() or executable.name != '晚安助手.exe'
            or not work.name.startswith('ahut-update-')
            or work.parent != Path(tempfile.gettempdir()).resolve()
            or not (executable.parent / '_internal').is_dir()):
        raise UpdateError('更新组件或目录不可用，请重新安装完整程序。')
    if hashlib.sha256(installer.read_bytes()).hexdigest() != release.sha256:
        raise UpdateError('安装包校验失败，请重新下载。')
    runner = work / 'AHUTUpdater.exe'
    shutil.copy2(source, runner)
    restart_args = []
    if '--data-dir' in sys.argv:
        restart_args = ['--data-dir', str(Path(data).resolve())]
    job = dict(work=str(work), target=str(executable.parent), installer=str(installer),
        sha256=release.sha256, version=release.version, parent=os.getpid(),
        wallpaper_pid=wallpaper_pid, result=str(Path(data) / 'update-result.json'),
        restart_args=restart_args)
    job_path = work / 'job.json'
    job_path.write_text(json.dumps(job), 'utf-8')
    try:
        return subprocess.Popen([str(runner), str(job_path)], creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
    except OSError:
        raise UpdateError('无法启动更新程序，请检查系统权限后重试。') from None


def consume_result(data):
    path = Path(data) / 'update-result.json'
    try:
        value = json.loads(path.read_text('utf-8'))
        path.unlink()
        return value
    except (OSError, ValueError):
        return None


def clean_download(path):
    """Delete only an updater-owned temporary workspace."""
    import shutil
    path = Path(path).resolve()
    if path.name.startswith('ahut-update-') and path.parent == Path(tempfile.gettempdir()).resolve():
        try:
            shutil.rmtree(path)
        except OSError:
            pass
