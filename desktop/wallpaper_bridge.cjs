// Adapter around wallpaper-engine-api 1.0.2, extended with scoped player controls.
// No shell commands, global wallpaper controls, or preview-image playback.
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {execFile}=require('node:child_process');
const {promisify}=require('node:util');
const execute=promisify(execFile);
let operation='read-request';
const {WallpaperEngineApi}=require('./vendor/wallpaper-api/node_modules/wallpaper-engine-api');
function local(p) {return typeof p==='string' && path.isAbsolute(p) && !p.startsWith('\\\\') && !p.startsWith('//');}
function silentProperties(data,properties) {
 // volume is the engine's shared output-volume property. Author switches also
 // stop music/ambient sources, without changing audio-reactive visual options.
 const props={...properties,volume:0};
 for(const [key,property] of Object.entries(data.general?.properties||{})) {
  const label=key+' '+(property.text||'');
  const sound=/(music|sound|volume|音乐|音量|声音|音效)/i.test(label);
  const reactive=/(react|visuali[sz]|spectrum|音频响应|音频反应|频谱)/i.test(label);
  if(!sound || reactive)continue;
  if(property.type==='bool')props[key]=false;
  if(property.type==='slider' && Number(property.min??0)<=0 && Number(property.max??100)>=0)props[key]=0;
 }
 return props;
}
async function run() {
 const job=JSON.parse(process.argv[2]);
 if(!local(job.engine)) throw Error('engine-path');
 const api=new WallpaperEngineApi(job.engine);
 const exe=['wallpaper64.exe','wallpaper32.exe'].map(n=>path.join(job.engine,n)).find(fs.existsSync);
 const command=async (args,raw=false)=>execute(exe,['-control',...args],{windowsHide:true,windowsVerbatimArguments:raw,timeout:10000,maxBuffer:1024*1024});
 if(job.action==='current') {
  // The upstream API's getConfig is reliable when getWallpaper returns no path.
  const config=await api.getConfig();
  const profiles=Object.entries(config).filter(([k,v])=>v && v.general && v.general.wallpaperconfig);
  profiles.sort((a,b)=>Number(b[0].toLowerCase()===os.userInfo().username.toLowerCase())-Number(a[0].toLowerCase()===os.userInfo().username.toLowerCase()));
  for(const [,profile] of profiles) {
   const selected=profile.general.wallpaperconfig.selectedwallpapers||{};
   const current=selected.Monitor0;
   if(!current || !local(current.file))continue;
   const project=path.join(path.dirname(current.file),'project.json');
   const data=JSON.parse(fs.readFileSync(project,'utf8'));
   if(!['scene','video','web'].includes(data.type))throw Error('unsupported-wallpaper-type');
   const properties=((profile.wproperties||{})[current.file]||{}).Monitor0||{};
   const props=silentProperties(data,properties);
   return {engine:job.engine,project,file:current.file,type:data.type,properties:props};
  }
  throw Error('no-current-wallpaper');
 }
 if(!/^AHUTLive-[a-f0-9-]+$/.test(job.name))throw Error('player-name');
 if(job.action==='open') {
  if(!local(job.project) || path.basename(job.project).toLowerCase()!=='project.json')throw Error('project-path');
  const data=JSON.parse(fs.readFileSync(job.project,'utf8'));
  if(!['scene','video','web'].includes(data.type))throw Error('unsupported-wallpaper-type');
  const p=job.placement;
  if(!p || !['x','y','width','height'].every(k=>Number.isInteger(p[k])) || p.width<16 || p.width>1280 || p.height<16 || p.height>720)throw Error('player-placement');
  operation='open-window';
  await command(['openWallpaper','-file',job.project,'-playInWindow',job.name,'-width',String(p.width),'-height',String(p.height),'-x',String(p.x),'-y',String(p.y),'-activate','false','-borderless','true']);
  const props=silentProperties(data,job.properties||{});
  operation='silence-window';
  // WPE parses RAW delimiters from the raw Windows command line. libuv's
  // ordinary quote escaping would leave backslashes in that JSON (exit 4).
  // All other arguments in this call are constants or the validated player ID.
  await command(['applyProperties','-location',job.name,'-properties','RAW~('+JSON.stringify(props)+')~END'],true);
  return {opened:true};
 }
 if(job.action==='close') {await command(['closeWallpaper','-location',job.name]);return {closed:true};}
 throw Error('unsupported-action');
}
run().then(v=>process.stdout.write(JSON.stringify(v))).catch(error=>{process.stdout.write(JSON.stringify({error:'wallpaper-operation-failed',operation,code:typeof error.code==='number'?error.code:'component-error',timeout:!!error.killed}));process.exitCode=1;});
