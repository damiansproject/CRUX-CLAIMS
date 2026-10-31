export const meta = {
  name: 'crux-extract-claims',
  description: 'Extract evidence-traceable claims (one agent per paper)',
}

// Keep in sync with skills/claim-extractor/scripts/lib/kinds.py (CLAIM_KINDS).
const CLAIM_KINDS = [
  'finding',
  'mechanism',
  'method',
  'limitation',
  'assumption',
  'problem',
  'other',
]

const ALLOWED_EFFORT = ['low', 'medium', 'high', 'xhigh', 'max']

let input = args
if (typeof input === 'string') {
  try {
    input = JSON.parse(input)
  } catch (error) {
    throw new Error(`crux-extract-claims args are not JSON: ${error.message}`)
  }
}

if (!input || typeof input !== 'object' || !Array.isArray(input.papers)) {
  throw new Error(
    'crux-extract-claims requires { papers: [{ paper_id, text_path }], shards_dir?, model?, effort?, extractor_prompt_path?, kinds?, max_claims_per_paper? }',
  )
}

const shardsDir =
  typeof input.shards_dir === 'string' && input.shards_dir.trim()
    ? input.shards_dir.trim().replace(/[\\/]+$/, '')
    : null
// Workers share this directory; every scratch file is keyed by paper_id.
const scratchDir = shardsDir ? `${shardsDir}/../.scratch` : '.scratch'
const writeShardPath =
  typeof input.write_shard_path === 'string' && input.write_shard_path.trim()
    ? input.write_shard_path.trim()
    : '.claude/skills/claim-extractor/scripts/write_shard.py'

function sanitizeShardPart(value) {
  return String(value).replace(/[^a-zA-Z0-9._-]+/g, '_').replace(/^_+|_+$/g, '') || 'id'
}

// Omit model/effort → inherit parent Claude Code session. Only set when args pass them.
function resolveAgentRouting(src) {
  const routing = {}
  if (typeof src.model === 'string' && src.model.trim()) {
    routing.model = src.model.trim()
  }
  if (typeof src.effort === 'string' && src.effort.trim()) {
    const value = src.effort.trim()
    if (!ALLOWED_EFFORT.includes(value)) {
      throw new Error(`effort must be one of ${ALLOWED_EFFORT.join(', ')}`)
    }
    routing.effort = value
  }
  return routing
}
const routing = resolveAgentRouting(input)

const promptPath =
  typeof input.extractor_prompt_path === 'string' && input.extractor_prompt_path.length > 0
    ? input.extractor_prompt_path
    : '.claude/skills/claim-extractor/prompts/claim-extractor.md'

let kinds = CLAIM_KINDS
if (input.kinds != null) {
  if (!Array.isArray(input.kinds) || input.kinds.length === 0) {
    throw new Error('kinds must be a non-empty array of claim kinds, or omitted')
  }
  for (const kind of input.kinds) {
    if (!CLAIM_KINDS.includes(kind)) {
      throw new Error(`unknown kind "${kind}"; expected one of ${CLAIM_KINDS.join(', ')}`)
    }
  }
  kinds = input.kinds
}

let maxClaims = null
if (input.max_claims_per_paper != null) {
  if (
    typeof input.max_claims_per_paper !== 'number' ||
    !Number.isInteger(input.max_claims_per_paper) ||
    input.max_claims_per_paper < 1
  ) {
    throw new Error('max_claims_per_paper must be a positive integer, or omitted')
  }
  maxClaims = input.max_claims_per_paper
}

const SOURCE_TYPES = [
  'journal',
  'preprint',
  'pdf',
  'gov',
  'news',
  'blog',
  'company',
  'social',
  'web',
]

const claimItem = {
  type: 'object',
  additionalProperties: false,
  required: ['kind', 'statement', 'quotes'],
  properties: {
    kind: {
      type: 'string',
      enum: CLAIM_KINDS,
    },
    statement: { type: 'string' },
    quotes: {
      type: 'array',
      minItems: 1,
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['text', 'locator'],
        properties: {
          text: { type: 'string' },
          locator: {
            type: 'object',
            additionalProperties: false,
            required: ['paper', 'page'],
            properties: {
              paper: { type: 'string' },
              page: { type: 'integer', minimum: 1 },
              section: { type: ['string', 'null'] },
              line: { type: ['integer', 'null'] },
            },
          },
        },
      },
    },
  },
}

const claimsArray = {
  type: 'array',
  items: claimItem,
}
if (maxClaims != null) {
  claimsArray.maxItems = maxClaims
}

const claimSchema = {
  type: 'object',
  additionalProperties: false,
  // paper_id is required in the schema so the agent echoes it, but the workflow
  // always overwrites it from the pipeline input after the agent returns.
  required: ['paper_id', 'claims', 'venue', 'source_type', 'suggested_quality', 'quality_rationale', 'gist'],
  properties: {
    paper_id: { type: 'string' },
    claims: claimsArray,
    // Bibliographic cues from the text (especially local PDFs that lack URL meta).
    venue: { type: ['string', 'null'] },
    source_type: { anyOf: [{ type: 'string', enum: SOURCE_TYPES }, { type: 'null' }] },
    suggested_quality: { type: ['number', 'null'], minimum: 0, maximum: 1 },
    quality_rationale: { type: ['string', 'null'] },
    title: { type: ['string', 'null'] },
    gist: { type: 'string' },
  },
}

const kindsLine =
  kinds.length === CLAIM_KINDS.length
    ? `Extract any of these kinds: ${CLAIM_KINDS.join(', ')}.`
    : `Only extract these kinds: ${kinds.join(', ')}. Skip claims that do not match.`

const maxLine =
  maxClaims == null
    ? 'No hard cap on claim count; prefer atomic claims over dumping.'
    : `Return at most ${maxClaims} claims for this paper (highest-evidence first).`

const ackSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['ok', 'shard', 'paper_id', 'claim_count'],
  properties: {
    ok: { type: 'boolean' },
    shard: { type: 'string' },
    paper_id: { type: 'string' },
    claim_count: { type: 'integer', minimum: 0 },
  },
}

function normalizeExtractResult(raw, paper) {
  if (!raw || typeof raw !== 'object') return null

  let claims = Array.isArray(raw.claims) ? raw.claims : []
  if (maxClaims != null && claims.length > maxClaims) {
    claims = claims.slice(0, maxClaims)
  }

  const venue = typeof raw.venue === 'string' && raw.venue.trim() ? raw.venue.trim() : null
  const sourceType =
    typeof raw.source_type === 'string' && SOURCE_TYPES.includes(raw.source_type)
      ? raw.source_type
      : null
  let suggestedQuality = null
  if (typeof raw.suggested_quality === 'number' && Number.isFinite(raw.suggested_quality)) {
    suggestedQuality = Math.max(0, Math.min(1, raw.suggested_quality))
  }
  const qualityRationale =
    typeof raw.quality_rationale === 'string' && raw.quality_rationale.trim()
      ? raw.quality_rationale.trim()
      : null
  const title = typeof raw.title === 'string' && raw.title.trim() ? raw.title.trim() : null
  const gist = typeof raw.gist === 'string' && raw.gist.trim() ? raw.gist.trim() : null

  return {
    paper_id: paper.paper_id,
    venue,
    source_type: sourceType,
    suggested_quality: suggestedQuality,
    quality_rationale: qualityRationale,
    title,
    gist,
    claims,
  }
}

async function extractWork(paper) {
  if (!paper || typeof paper.paper_id !== 'string' || typeof paper.text_path !== 'string') {
    throw new Error('every paper needs paper_id and text_path')
  }

  const textScratch = `${scratchDir}/text-${sanitizeShardPart(paper.paper_id)}.txt`
  const prompt = `
1. Read the extractor instructions at: ${promptPath}
2. Read the paper text JSON at: ${paper.text_path}
   If you copy the text to a scratch file, use exactly ${textScratch}. Other workers share that directory; never a fixed name like paper.txt.
3. Set paper_id exactly to "${paper.paper_id}" (copy this string verbatim).
4. ${kindsLine}
5. ${maxLine}
6. Return structured output matching the schema.
`

  const raw = await agent(prompt, {
    label: `claims:${paper.paper_id}`,
    model: routing.model, // undefined → inherit session model
    effort: routing.effort,
    schema: claimSchema,
  })
  return normalizeExtractResult(raw, paper)
}

async function extractWriteShard(normalized, paper) {
  if (!normalized) return null
  const shardPath = `${shardsDir}/${sanitizeShardPart(paper.paper_id)}.json`
  // scratchDir sits outside the stage dir — merge_extract globs *.json there.
  const tmpPath = `${scratchDir}/tmp-${sanitizeShardPart(paper.paper_id)}.json`
  const payload = JSON.stringify(normalized)
  const prompt = `
Persist one extract shard. Do not rethink the science.

1. Write this exact JSON to temporary file path:
${tmpPath}

PAYLOAD:
${payload}

2. Run (python3, then py -3, then python):
python3 ${writeShardPath} --out ${JSON.stringify(shardPath)} --stage extract --file ${JSON.stringify(tmpPath)}

3. Delete the temporary file ${tmpPath} after write_shard.py succeeds.

4. Return structured ack only. Set ok true only if write_shard.py succeeded.
paper_id="${paper.paper_id}" claim_count=${normalized.claims.length} shard=${JSON.stringify(shardPath)}
`

  const ack = await agent(prompt, {
    label: `shard-extract:${paper.paper_id}`,
    model: routing.model, // undefined → inherit session model
    effort: routing.effort,
    schema: ackSchema,
  })
  if (!ack || ack.ok !== true) return null
  return {
    paper_id: paper.paper_id,
    claim_count: normalized.claims.length,
    shard: typeof ack.shard === 'string' ? ack.shard : shardPath,
  }
}

const results = shardsDir
  ? await pipeline(input.papers, extractWork, extractWriteShard)
  : await pipeline(input.papers, extractWork)

const empty = []
for (const result of results) {
  if (!result) continue
  if (shardsDir) {
    if (result.claim_count === 0) empty.push(result.paper_id)
  } else if (Array.isArray(result.claims) && result.claims.length === 0) {
    empty.push(result.paper_id)
  }
}

return {
  model: routing.model ?? null,
  effort: routing.effort ?? null,
  kinds,
  max_claims_per_paper: maxClaims,
  papers: input.papers,
  shards_dir: shardsDir,
  results: results.filter(Boolean),
  empty,
  failed: results
    .map((result, index) => (result ? null : input.papers[index]?.paper_id ?? `index-${index}`))
    .filter(Boolean),
}
