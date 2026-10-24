// One schema shared by the Host and browser; strict codecs at the Harness boundary.
import { z } from 'zod';
import { createTypertRemoteInfo } from '@deepseek-ai/dsh-typert-protocol/remote-info';

export const translateSchema = z.strictObject({
  pdf: z.string().min(1), pages: z.string().optional(), workers: z.number().int().min(1).max(8).optional(),
  imageQuality: z.enum(['safe', 'auto', 'compact']).optional(), thinking: z.enum(['auto', 'off', 'on']).optional(),
  renderOnly: z.boolean().optional(), outputDir: z.string().optional(), background: z.boolean().optional(), aiReview:z.boolean().optional(),
});
export const requestSchema = z.discriminatedUnion('action', [
  z.strictObject({ action:z.literal('status'), sessionId:z.string().optional() }),
  z.strictObject({ action:z.literal('browse'), path:z.string().optional(), directories:z.boolean().optional() }),
  z.strictObject({ action:z.literal('pick'), kind:z.enum(['pdf','directory']) }),
  z.strictObject({ action:z.literal('inspect'), pdf:z.string(), pages:z.string().optional() }),
  z.strictObject({ action:z.literal('start'), sessionId:z.string().min(1), args:translateSchema }),
  z.strictObject({ action:z.literal('cancel'), sessionId:z.string().min(1), jobId:z.string() }),
  z.strictObject({ action:z.literal('settings'), outputDir:z.string().min(1).optional(), aiReview:z.boolean().optional() }),
  z.strictObject({ action:z.literal('caches') }),
  z.strictObject({ action:z.literal('prepareClear'), identity:z.string().regex(/^[a-f0-9]{16}$/) }),
  z.strictObject({ action:z.literal('clear'), identity:z.string().regex(/^[a-f0-9]{16}$/), token:z.string() }),
  z.strictObject({ action:z.literal('open'), sessionId:z.string().min(1), jobId:z.string(), kind:z.enum(['output','markdown','project','report','document']) }),
]);
const codec = {mode:'strict', typeSymbol:'dsh-pdf-translator#request', create:()=>requestSchema};
export const remoteInfo = createTypertRemoteInfo({package:'dsh-pdf-translator', methods:{
  'pdfTranslator/call': {service:'pdfTranslator', invocation:{kind:'direct'},
    parameters:[{name:'request', source:'json', codec, strictCodec:codec}],
    result:{mode:'strict', typeSymbol:'dsh-pdf-translator#result', create:()=>z.json()},
  },
}}, z);
export const hostInfo = {package:'dsh-pdf-translator', face:'host', schemas:[],
  get invocations(){return remoteInfo.descriptors;}, model:{services:[],events:[],objects:[]}};
