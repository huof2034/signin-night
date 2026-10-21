"""Public release discovery; never reads credentials or executes downloads."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

VERSION = '1.5.1'
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
    if not isinstance(assets, list) or not any(isinstance(a, dict) and a.get('name') == name
            and a.get('browser_download_url') == installer and isinstance(a.get('size'), int)
            and a['size'] > 0 and a.get('state') == 'uploaded' for a in assets):
        raise UpdateError('新版 Windows 安装包尚未就绪，请稍后重试。')
    return Release(version, page, installer, latest > version_tuple(current))


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
