// MSW handlers for manual mode (decision 111): the two demo tasks the mock server seeds (a concept request and a 3D
// request built by the tripo-v3 manifest), and uploads that mark a task submitted.
import { http, HttpResponse } from 'msw';
import type { ManualTask } from '@petpop/core';
import { assetUrl } from '@petpop/core';

const SETTINGS = ['model: v3.1-20260211', 'texture: true', 'pbr: false', 'texture_quality: detailed', 'texture_alignment: original_image', 'orientation: default', 'face_limit: 200000', 'model_seed: 7', 'texture_seed: 7'];
const base = { job_id: 'j_manual_demo', status: 'pending', provider: 'tripo (manual)', vendor: 'Tripo3D', manifest: 'tripo-v3 v1', species: 'dog', pet_name: 'Biscuit', breed_label: 'Pembroke Welsh Corgi', batch_id: null, created_at: '2026-10-31T09:00:00Z', submitted_at: null, result_name: null } as const;

export const MANUAL_TASKS: ManualTask[] = [
  {
    ...base,
    task_id: 'j_manual_demo.text-to-image-demo',
    capability: 'text_to_image',
    title: 'Concept image (Tripo text to image)',
    route: 'POST /v3/generation/text-to-image',
    prompt: 'a chibi vinyl collectible figurine of a Pembroke Welsh Corgi dog, entire figure in sharp focus, sitting pose, oversized round head',
    negative_prompt: 'realistic fur, photorealistic, text, watermark, bokeh, depth of field',
    request: { prompt: 'a chibi vinyl collectible figurine of a Pembroke Welsh Corgi dog, entire figure in sharp focus', negative_prompt: 'realistic fur, photorealistic' },
    settings: [],
    inputs: [],
    instructions: ['In Tripo Studio, open image generation (text to image).', 'Paste the prompt; paste the negative prompt if the tool has a field for it.', 'Generate, download the image and upload it here.'],
    expects: { kind: 'image', accept: ['.png', '.jpg', '.jpeg', '.webp'] },
  },
  {
    ...base,
    task_id: 'j_manual_demo.image-to-model-demo',
    capability: 'image_to_model',
    title: '3D model from the concept (Tripo image to 3D)',
    route: 'POST /v3/generation/image-to-model',
    prompt: null,
    negative_prompt: null,
    request: { input: '<upload input.png>', model: 'v3.1-20260211', texture: true, pbr: false, texture_quality: 'detailed', face_limit: 200000, model_seed: 7, texture_seed: 7 },
    settings: SETTINGS,
    inputs: [{ name: 'input.png', url: assetUrl('fixtures/pets/biscuit/concept.png') }],
    instructions: ['Download the input image below.', 'In Tripo Studio, open image to 3D and upload it.', 'Match the settings below; keep private generation on.', 'Download the GLB and upload it here.'],
    expects: { kind: 'model', accept: ['.glb'] },
  },
];

const tasks = MANUAL_TASKS.map((t) => ({ ...t }));

export const manualHandlers = [
  http.get('/api/v1/studio/manual', ({ request }) => {
    const status = new URL(request.url).searchParams.get('status') ?? 'pending';
    return HttpResponse.json({ pending: tasks.filter((t) => t.status === 'pending').length, items: tasks.filter((t) => status === 'all' || t.status === status) });
  }),
  http.get('/api/v1/studio/manual/:id', ({ params }) => {
    const t = tasks.find((x) => x.task_id === params.id);
    return t ? HttpResponse.json(t) : HttpResponse.json({ detail: `unknown manual task ${params.id}` }, { status: 404 });
  }),
  http.post('/api/v1/studio/manual/:id/result', async ({ params, request }) => {
    const t = tasks.find((x) => x.task_id === params.id);
    if (!t) return HttpResponse.json({ detail: `unknown manual task ${params.id}` }, { status: 404 });
    if (t.status !== 'pending') return HttpResponse.json({ detail: 'this task already has its output' }, { status: 409 });
    const file = (await request.formData()).get('file') as File | null;
    const ext = file?.name.includes('.') ? `.${file.name.split('.').pop()!.toLowerCase()}` : '';
    if (!file || !t.expects.accept.includes(ext)) return HttpResponse.json({ detail: `expected ${t.expects.accept.join(' or ')}` }, { status: 422 });
    Object.assign(t, { status: 'submitted', submitted_at: new Date().toISOString(), result_name: file.name });
    return HttpResponse.json(t);
  }),
];
