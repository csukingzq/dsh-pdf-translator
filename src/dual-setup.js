import path from 'node:path';
import fs from 'node:fs';
import { SetupController } from './setup.js';
import { root } from './paths.js';

class MineruSetupController extends SetupController {
  constructor(config, options, translation) {
    super(config, {...options, profile:'pdf2zh', scriptPath:path.join(root,'scripts/setup-mineru.ps1')});
    this.translation=translation;
  }
  pythonPath(){return path.join(this.dataDir,'.venv-mineru',process.platform==='win32'?'Scripts/python.exe':'bin/python');}
  hasPython(){return fs.existsSync(this.pythonPath());}
  markerPath(){return path.join(this.runtimeDir,'mineru.json');}
  marker(){const m=super.marker();return this.hasPython()&&m.version==='4.2.3'?m:{version:''};}
  async prime(){await this.translation.prime();return super.prime();}
  async probe(){
    if(this.marker().version){this.engine={ready:true,version:'4.2.3',error:'',probed:true};return this.engine;}
    if(this.engine.probed)return this.engine;
    if(!this.allowProbe||!this.hasPython())return this.engine;
    const r=await this.exec(this.pythonPath(),['-c',"from mineru.parser import parse; from mineru.render import render_pdf; import importlib.metadata as m; print(m.version('mineru'))"]);
    const version=r.out.trim().split('\n').at(-1).trim();
    this.engine={ready:r.code===0&&version==='4.2.3',version,error:'',probed:true};
    return this.engine;
  }
  snapshot(){
    const own=super.snapshot(), pdf=this.translation.snapshot();
    return {...own,ready:own.ready&&pdf.ready,runtimeReady:own.runtimeReady&&pdf.runtimeReady,
      missing:{...own.missing,python:own.missing.python||pdf.missing.python,engine:own.missing.engine||pdf.missing.engine}};
  }
}

export class DualSetupController {
  constructor(config = {}, options = {}) {
    const pdf2zh=new SetupController(config,{...options,profile:'pdf2zh'});
    this.controllers={pdf2zh,mineru:new MineruSetupController(config,options,pdf2zh)};
  }
  get running(){return Object.values(this.controllers).some(c=>c.running);}
  controller(engine='pdf2zh'){
    const c=this.controllers[engine];
    if(!c)throw new Error('未知翻译引擎。');
    return c;
  }
  prime(engine){return engine ? this.controller(engine).prime() : Promise.all(Object.values(this.controllers).map(c=>c.prime()));}
  snapshot(engine='pdf2zh'){return this.controller(engine).snapshot();}
  snapshots(){return Object.fromEntries(Object.entries(this.controllers).map(([key,c])=>[key,c.snapshot()]));}
  start(engine='pdf2zh'){
    if(this.running)throw new Error('已有环境安装运行，请等待完成。');
    return this.controller(engine).start();
  }
  cancel(){for(const c of Object.values(this.controllers))if(c.running)return c.cancel();return this.snapshot();}
  saveConfig(input){return this.controller(input.engine).saveConfig(input);}
}
