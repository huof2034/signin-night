"""Fetch the pinned, redistributable wallpaper helpers; never run installers."""
from pathlib import Path
import argparse, base64, hashlib, io, json, shutil, subprocess, tarfile, urllib.request, zipfile

DEST=Path(__file__).resolve().parent/'vendor'

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'AHUTSignIn-build'})
    with urllib.request.urlopen(req,timeout=60) as r:return r.read()

def npm(name,version):
    metadata=json.loads(fetch(f'https://registry.npmjs.org/{name}/{version}'))
    payload=fetch(metadata['dist']['tarball'])
    assert 'sha512-'+base64.b64encode(hashlib.sha512(payload).digest()).decode()==metadata['dist']['integrity']
    root=DEST/'wallpaper-api/node_modules'/name
    with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as archive:
        for entry in archive:
            relative=Path(entry.name).relative_to('package')
            if not entry.isfile() or '..' in relative.parts or relative.suffix=='.map':continue
            target=root/relative
            if not target.resolve().is_relative_to(root.resolve()):raise RuntimeError('unsafe package entry')
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.extractfile(entry).read())
    return {'version':version,'url':metadata['dist']['tarball'],'sha256':hashlib.sha256(payload).hexdigest()}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--node',required=True);args=parser.parse_args()
    DEST.mkdir(exist_ok=True);sources={}
    sources['wallpaper-engine-api']=npm('wallpaper-engine-api','1.0.2')
    sources['uuid']=npm('uuid','11.1.0')
    node=Path(args.node);version=subprocess.check_output([str(node),'--version'],text=True).strip()
    shutil.copyfile(node,DEST/'wallpaper-api/node.exe')
    (DEST/'wallpaper-api/NODE-LICENSE.txt').write_bytes(fetch(f'https://raw.githubusercontent.com/nodejs/node/{version}/LICENSE'))
    sources['node']={'version':version,'url':'https://nodejs.org/','sha256':hashlib.sha256(node.read_bytes()).hexdigest()}
    url='https://github.com/notscuffed/repkg/releases/download/v0.4.0-alpha/RePKG.zip'
    payload=fetch(url);folder=DEST/'repkg';folder.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name in ('RePKG.exe','THIRD-PARTY-NOTICES.txt'):(folder/name).write_bytes(archive.read(name))
    (folder/'LICENSE.txt').write_bytes(fetch('https://raw.githubusercontent.com/notscuffed/repkg/v0.4.0-alpha/LICENSE'))
    sources['RePKG']={'version':'0.4.0-alpha','url':url,'sha256':hashlib.sha256(payload).hexdigest()}
    url='https://files.pythonhosted.org/packages/6c/02/cdb3c75e60863e94fbd53c2b3607e61af5d464a4f9301e45897fcb08dbfa/windows_capture-2.0.1-cp39-abi3-win_amd64.whl'
    payload=fetch(url);assert hashlib.sha256(payload).hexdigest()=='209c2318e2168802b9afd1005e99499639e8835e71a1e188a3ddc77c7ccc3f04'
    folder=DEST/'capture';folder.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name in archive.namelist():
            if name.endswith('.pyd'):(folder/'windows_capture.pyd').write_bytes(archive.read(name))
            elif '/licenses/' in name:(folder/Path(name).name).write_bytes(archive.read(name))
    sources['windows-capture']={'version':'2.0.1','url':url,'sha256':hashlib.sha256(payload).hexdigest()}
    (DEST/'SOURCES.json').write_text(json.dumps(sources,indent=2),encoding='utf-8')
    print('Pinned wallpaper helpers and licenses prepared.')

if __name__=='__main__':main()
