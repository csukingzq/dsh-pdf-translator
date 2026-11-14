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
    description: '用 pdf2zh-next / BabelDOC 将 PDF 翻译成中文，保留原版式（公式、图表、目录、双栏原位替换），输出单语译文 PDF（mono）和双语对照 PDF（dual）。每次任务新建一个输出子目录，里面是 mono、dual 两个 PDF 和 report.json。只翻译指定页码，其余页保留原文；表格单元格文字默认不翻译；扫描件需要先有文本层。首次使用必须先准备运行环境并填写模型配置：失败时按提示引导用户打开 PDF 翻译面板完成，不要尝试在终端手改配置。翻译会把原文发送到用户配置的模型接口并产生 API 费用，大文档耗时较长；建议先指定少量 pages 试跑。成功后遵循结果 completionPolicy：只读取一次 job_output，简短回复并附 mono 与 dual 两个 PDF 链接。',
    parameters: {
      pdf: { ...string, required: true, description: '本地 PDF 绝对路径' },
      pages: { ...string, description: 'all 或 1,3-5，默认 all' },
      workers: { ...number, description: '并发翻译请求数 1–8，默认 4' },
      outputDir: { ...string, description: '本次输出目录的绝对路径；省略使用面板配置，不改变默认值。' },
      background: { type:'boolean', description:'默认 true：返回 Harness 后台任务 ID，使用原生 job_output 获取结果，不要反复轮询。false 等待最终结果。' },
    },
    output: output({ output: string, dual: string, report: string, status: string, pages: number, engine: string }),
    async execute(args, exec) {
      if (!args.pdf.trim()) throw new Error('PDF 路径不能为空。');
      if (args.workers !== undefined && (!Number.isInteger(args.workers) || args.workers < 1 || args.workers > 8)) {
        throw new Error('workers 必须是 1 至 8 的整数。');
      }
      return manager.start(args, exec.agent?.id, exec);
    },
  }));
  ctx.tools.register(defineTool({
    name:'pdf_cache_list', description:'只读查看 PDF 翻译缓存。翻译引擎共享缓存只能由用户打开 PDF 翻译面板、打开缓存窗口并确认后清理；不要用文件工具代替用户删除缓存。',
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
    parameters: {}, output: output({ python: string, engine: { type:'object', properties:{}, additionalProperties:true }, pymupdf: string, model_configured: { type: 'boolean' }, plugin_root: string, data_dir: string, config_path: string, engine_cache_dir: string, runtime_dir: string }),
    execute: (_args, exec) => call({ operation: 'doctor' }, exec),
  }));
}
