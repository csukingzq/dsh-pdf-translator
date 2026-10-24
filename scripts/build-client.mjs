import { build } from 'esbuild';
import { mkdir, writeFile } from 'node:fs/promises';
// Harness 0.2.1 lazy-CJS factory protocol; all non-platform imports are bundled.
const result=await build({entryPoints:['src/client.jsx'],bundle:true,write:false,format:'cjs',platform:'browser',target:'es2022',
  external:['react','react-dom/client'],loader:{'.css':'text'},jsx:'automatic',minify:true});
await mkdir('lib',{recursive:true});
await writeFile('lib/client.js',`window.__ModuleLoader__.load({id:"dsh-pdf-translator",factory:(require)=>{var module={exports:{}};var exports=module.exports;\n${result.outputFiles[0].text}\nreturn module.exports;}});\n`);
