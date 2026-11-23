import Schema from '@deepseek-ai/schemastery';
import { defineTool } from '@deepseek-ai/dsh-tools';
import { runPython } from './runner.js';
import { TranslatorManager } from './manager.js';
import { TranslatorService } from './service.js';
import { installCompletionPolicy } from './completion-policy.js';

export const name = 'ai-pdf-translator';
export const inject = ['tools'];
export const Config = Schema.object({
  pythonPath: Schema.string().default('').description('Python 可执行文件；默认使用插件 .venv。'),
  configPath: Schema.string().default('').description('模型配置文件绝对路径；默认使用插件 config.json。'),
  dataDir: Schema.string().default('').description('输出与缓存目录；默认使用插件目录。'),
  outputDir: Schema.string().default('').description('初始输出目录；默认 dataDir/outputs，可在面板保存设置。'),
  timeoutMs: Schema.number().min(1000).default(3600000).description('单次任务超时（毫秒）。'),
});

const string = { type: 'string' };
const number = { type: 'number' };
const output = (properties) => ({
  schema: { type: 'object', properties, additionalProperties: true },
  render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
});

export function apply(ctx, config = {}) {
  const manager = new TranslatorManager(ctx, config);
  installCompletionPolicy(ctx, manager);
  ctx.effect(() => () => manager.dispose());
  ctx.inject(['typert'], apiCtx => { new TranslatorService(apiCtx, manager); });
  const controller = new AbortController();
  ctx.effect(() => () => controller.abort());
  const call = (request, exec) => runPython(request, config,
    exec.signal ? AbortSignal.any([exec.signal, controller.signal]) : controller.signal);
  ctx.tools.register(defineTool({
    name: 'pdf_translate',
    description: '将 PDF 翻译成中文。pdf2zh（推荐）保留文本 PDF 的版式，输出 output 单语 PDF 和 dual 双语 PDF。mineru 在本机用 MinerU 识别扫描件、生成可选中文字的 PDF，再自动用 PDF2zh 翻译，另输出 mineru 识别版 PDF。两条路线共用翻译模型配置；不再使用视觉大模型 OCR、LaTeX 重排或 AI 核验。仅处理和输出所选页码，例如 2-4 输出 3 页；大文档建议先选少量页面试跑。识别在本机完成，翻译会向所配置接口发送识别文本并产生 API 费用。环境未就绪时引导用户打开面板一键准备环境和填写配置。成功后遵循 completionPolicy。',
    parameters: {
      engine:{...string,enum:['pdf2zh','mineru'],description:'pdf2zh（文本 PDF，推荐）或 mineru（本机识别扫描件后自动 PDF2zh 翻译）；省略使用面板设置。'},
      pdf: { ...string, required: true, description: '本地 PDF 绝对路径' },
      pages: { ...string, description: 'all 或 1,3-5，默认 all' },
      workers: { ...number, description: '并发翻译请求数 1–8，默认 4' },
      outputDir: { ...string, description: '本次输出目录的绝对路径；省略使用面板配置，不改变默认值。' },
      background: { type:'boolean', description:'默认 true：返回 Harness 后台任务 ID，使用原生 job_output 获取结果，不要反复轮询。false 等待最终结果。' },
    },
    output: output({ output: string, dual: string, mineru: string, status: string, pages: number, engine: string }),
    async execute(args, exec) {
      if (!args.pdf.trim()) throw new Error('PDF 路径不能为空。');
      if (args.workers !== undefined && (!Number.isInteger(args.workers) || args.workers < 1 || args.workers > 8)) {
        throw new Error('workers 必须是 1 至 8 的整数。');
      }
      return manager.start(args, exec.agent?.id, exec);
    },
  }));
  ctx.tools.register(defineTool({
    name:'pdf_cache_list', description:'只读查看两种引擎的逐文档翻译缓存。缓存只能由用户打开 PDF 翻译面板、打开缓存窗口并确认后清理；不要用文件工具代替用户删除缓存。',
    parameters:{}, output:output({entries:{type:'array',items:{type:'object',properties:{},additionalProperties:true}}}),
    execute:()=>manager.caches(),
  }));
  ctx.tools.register(defineTool({
    name:'pdf_panel', description:'仅在用户明确要求时显示或隐藏 PDF 翻译面板，可定位输出目录操作或打开缓存窗口。不会翻译或清理缓存；不要在启动翻译时自动打开。',
    parameters:{section:{...string,enum:['translation','outputs','cache']},visible:{type:'boolean'}},
    output:output({requested:{type:'boolean'},message:string}),
    execute:(args,exec)=>manager.panel(exec.agent?.id,args.section,args.visible),
  }));
  ctx.tools.register(defineTool({
    name: 'pdf_inspect', description: '读取本地 PDF 页数、文件大小并验证页码范围，不发送内容到模型。',
    parameters: { pdf: { ...string, required: true }, pages: string },
    output: output({ path: string, pages: number, bytes: number, selected_pages: { type:'array', items:{type:'number'} } }),
    execute: (args, exec) => call({ ...args, operation: 'inspect' }, exec),
  }));
  ctx.tools.register(defineTool({
    name: 'pdf_translator_doctor', description: '检查 Python、pdf2zh-next 翻译引擎与模型配置是否存在，不调用模型、不返回密钥；同时显示插件、数据、配置和缓存目录。若检查失败或环境未就绪，引导用户打开 PDF 翻译面板点击“一键准备环境”并填写模型配置，不要让用户手改 JSON 或在终端跑脚本。',
    parameters: {engine:{...string,enum:['pdf2zh','mineru']}}, output: output({ python: string, engine: { type:'object', properties:{}, additionalProperties:true }, pymupdf: string, model_configured: { type: 'boolean' }, plugin_root: string, data_dir: string, config_path: string, engine_cache_dir: string, runtime_dir: string }),
    execute: (args, exec) => call({ operation: 'doctor',engine:args.engine||'pdf2zh' }, exec),
  }));
}
