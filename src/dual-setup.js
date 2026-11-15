import path from 'node:path';
import { SetupController } from './setup.js';
import { root } from './paths.js';

export class DualSetupController {
  constructor(config = {}, options = {}) {
    this.controllers = Object.fromEntries(['pdf2zh', 'ocr'].map(engine => [engine,
      new SetupController(config, {...options, profile:engine,
        scriptPath:path.join(root,'scripts',engine==='ocr'?'setup-ocr.ps1':'setup.ps1')})]));
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
