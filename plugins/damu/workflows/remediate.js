export const meta = {
  name: 'damu-remediate',
  description: 'Judges a captured UI for AI-slop tells. Reads per-route screenshots + extracted CSS facts (never the live browser), establishes the app\'s apparent purpose and audience, runs 8 blind per-tell lenses (typography, color, gradients & borders, shape & depth, layout soul, motion, iconography, copy), adversarially verifies every candidate by refuting it as intentional given the app context, runs a completeness critic over uncovered tells and pages, then synthesizes a per-page deliberate/mixed/slop verdict with a ranked, source-anchored change list tagged by confidence and risk. Report only — the orchestrator handles any apply. Governing rule: every tell is sometimes correct, so a finding is real only when the choice looks unmotivated and uniform.',
  whenToUse: 'Driven by /damu:remediate after the orchestrator captures screenshots + facts.json for each route. Not run directly.',
  phases: [
    { title: 'Context' },
    { title: 'Lenses' },
    { title: 'Verify' },
    { title: 'Critic' },
    { title: 'Synthesize' },
  ],
}

// ---------------------------------------------------------------------------
// Inputs
// ---------------------------------------------------------------------------
const runDir = args?.runDir
const catalogPath = args?.catalogPath
const appContext = (args?.appContext || '').trim() || '(none provided)'
if (!runDir || !catalogPath) {
  return { error: 'damu-remediate requires args.runDir and args.catalogPath' }
}
const factsPath = `${runDir}/facts.json`
const shotsDir = `${runDir}/shots`
const sourceMapPath = `${runDir}/source-map.json`
const manifestPath = `${runDir}/manifest.json`

// Shared grounding every agent must load before judging.
const GROUND = `
ARTIFACTS — read these yourself, do not trust this prompt's summary of them:
- Slop catalog (the tells, fixes, fact-signals, and "legit when" exceptions): ${catalogPath}
- Extracted CSS facts per route: ${factsPath}
- Screenshots (PNG, read them with vision): ${shotsDir}/  (also see ${manifestPath} for the route list)
- Best-effort source map (where styles/components live): ${sourceMapPath}

APP CONTEXT supplied by the user (audience / brand / vibe; may be empty): ${appContext}

GOVERNING RULE: every slop tell is sometimes the correct choice. The slop is the pattern applied by
default, uniformly, with no reason — not the pattern itself. Judge from the screenshots AND the facts
together; a fact threshold alone is not a finding until the screenshot confirms it reads as unmotivated.`

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------
const CONTEXT_SCHEMA = {
  type: 'object',
  properties: {
    apparent_purpose: { type: 'string', description: 'What this product is FOR, in one sentence, from the screenshots.' },
    audience: { type: 'string', description: 'Who it appears aimed at (e.g. developers, kids, finance pros, music fans).' },
    intended_aesthetic: { type: 'string', description: 'The apparent design intent, if any — or "no discernible intent / defaulted" stated plainly.' },
    legit_patterns: { type: 'array', items: { type: 'string' }, description: 'Slop-adjacent patterns that would be LEGITIMATE for this product (e.g. "card grid — it is a dashboard", "rounded+emoji — kids app"). Used to pre-empt false findings.' },
    routes: { type: 'array', items: { type: 'string' }, description: 'Route slugs found in the manifest.' },
  },
  required: ['apparent_purpose', 'audience', 'intended_aesthetic', 'legit_patterns', 'routes'],
}

const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          slop_id: { type: 'string', description: 'SLOP-NN from the catalog.' },
          title: { type: 'string', description: 'Short, specific — name the actual thing seen, not the category.' },
          routes: { type: 'array', items: { type: 'string' }, description: 'Route slug(s) where it appears.' },
          severity: { type: 'string', enum: ['high', 'medium', 'low'] },
          evidence: { type: 'string', description: 'The fact signal (cite the numbers from facts.json) AND what the screenshot shows. Both.' },
          fix: { type: 'string', description: 'The concrete change to make.' },
          source_hint: { type: 'string', description: 'Best guess at the file/token to change from the source map, or "unknown".' },
        },
        required: ['slop_id', 'title', 'routes', 'severity', 'evidence', 'fix'],
      },
    },
  },
  required: ['findings'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    intentional: { type: 'boolean', description: 'True if this choice is plausibly deliberate / justified for THIS product — i.e. the finding should be DROPPED.' },
    refutation: { type: 'string', description: 'The case that it is intentional (the "legit when" argument), or why that case fails.' },
    confidence: { type: 'string', enum: ['HIGH', 'MEDIUM', 'LOW'], description: 'Confidence that this is genuinely slop (only meaningful when intentional=false).' },
    risk: { type: 'string', enum: ['low', 'med', 'high'], description: 'Blast radius of applying the fix.' },
  },
  required: ['intentional', 'refutation', 'confidence', 'risk'],
}

const REPORT_SCHEMA = {
  type: 'object',
  properties: {
    overall_verdict: { type: 'string', description: 'One paragraph: does this UI read as AI-generated, and the single biggest lever.' },
    pages: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          route: { type: 'string' },
          verdict: { type: 'string', enum: ['deliberate', 'mixed', 'slop'] },
          note: { type: 'string' },
        },
        required: ['route', 'verdict', 'note'],
      },
    },
    ranked_findings: {
      type: 'array',
      description: 'The confirmed findings, ordered highest-leverage first.',
      items: {
        type: 'object',
        properties: {
          slop_id: { type: 'string' },
          title: { type: 'string' },
          routes: { type: 'array', items: { type: 'string' } },
          severity: { type: 'string', enum: ['high', 'medium', 'low'] },
          confidence: { type: 'string', enum: ['HIGH', 'MEDIUM', 'LOW'] },
          risk: { type: 'string', enum: ['low', 'med', 'high'] },
          evidence: { type: 'string' },
          fix: { type: 'string' },
          source_hint: { type: 'string' },
          caveat: { type: 'string', description: 'The surviving "why it might be fine" note from verification, or empty.' },
          auto_applicable: { type: 'boolean', description: 'True only when confidence HIGH, risk low, and not a copy finding (SLOP-08/-11).' },
        },
        required: ['slop_id', 'title', 'routes', 'severity', 'confidence', 'risk', 'evidence', 'fix', 'auto_applicable'],
      },
    },
  },
  required: ['overall_verdict', 'pages', 'ranked_findings'],
}

// ---------------------------------------------------------------------------
// Lenses — each owns a group of tells and judges all routes blindly.
// ---------------------------------------------------------------------------
const LENSES = [
  { key: 'typography', tells: 'SLOP-01 (font chaos), SLOP-16 (the AI-startup display serif)',
    focus: 'Count distinct rendered font families (distinctFonts/topFonts). Is there a type system or a pile of competing faces? Is the hero set in the cliché high-contrast AI-startup serif paired with a default geometric sans?' },
  { key: 'color', tells: 'SLOP-02 (purple/indigo on near-black/blue), SLOP-18 (forced monochrome), SLOP-14 (neon gradients)',
    focus: 'Look at topTextColors/topBgColors and the screenshots. Is it the default violet/indigo-on-near-black AI wash? Or forced monochrome with no functional accent? Or oversaturated neon? Was the palette chosen for a reason?' },
  { key: 'gradients_borders', tells: 'SLOP-05 (ugly/default gradients), SLOP-15 (neon gradient borders)',
    focus: 'gradients.count/samples and the screenshots. Muddy purple→blue default gradients as the house surface? The glowing neon gradient card/button border ring? Used by default vs. one earned focal element?' },
  { key: 'shape_depth', tells: 'SLOP-12 (over-rounded corners), SLOP-13 (huge drop shadows)',
    focus: 'radii.largeShare/max and shadows.bigShare/maxBlur with the screenshots. Are large radii and big soft shadows applied near-universally across unlike elements, floating the whole UI? Or a deliberate, mostly-modest scale?' },
  { key: 'layout_soul', tells: 'SLOP-07 (everything-is-a-24px-card), SLOP-17 (out-of-box shadcn), SLOP-09 (default-Tailwind smell)',
    focus: 'cardLikeCount, shadcnTokensPresent, and the screenshots. Is every section an identical bordered+shadowed 24px card in a grid? Untouched shadcn defaults? The default-Tailwind look with no token tuning? Does any content breathe outside a box? Where is the soul — any evidence of a deliberate human choice?' },
  { key: 'motion', tells: 'SLOP-03 (gratuitous parallax), SLOP-04 (weird hovers)',
    focus: 'parallaxFixedBg and the screenshots/structure. A scroll-parallax background with no narrative reason? Note that hover states are hard to see in a static shot — flag parallax confidently; flag hovers only if the structure/classes strongly suggest broad scale/tilt/glow.' },
  { key: 'iconography', tells: 'SLOP-06 (recycled stock icons), SLOP-10 (icon/emoji overuse), SLOP-11 (mismatched icon/emoji)',
    focus: 'emojiCount and the screenshots. The same rocket/bolt/shield recycled across features? An icon or emoji on every heading/bullet/button? Icons/emoji that do not match their label (e.g. a rocket next to "Billing")?' },
  { key: 'copy', tells: 'SLOP-08 (empty filler copy)',
    focus: 'fillerHits and the visible text in the screenshots. Headlines/body that are grammatically fine but say nothing ("seamless, cutting-edge, empower")? Surface specifics — but mark copy findings clearly: they are for the human to rewrite, never auto-fixed.' },
]

// ---------------------------------------------------------------------------
// Phase: Context
// ---------------------------------------------------------------------------
phase('Context')
const ctx = await agent(
  `${GROUND}\n\nYou are the CONTEXT pass. Read the manifest, the facts, and at least the home + one other\nscreenshot. Establish what this product is, who it is for, and whether it has a discernible design\nintent. Crucially, list the slop-adjacent patterns that would be LEGITIMATE here, so later lenses\ndon't flag them. Be concrete and honest — "no discernible intent, looks defaulted" is a valid finding.`,
  { label: 'context', phase: 'Context', schema: CONTEXT_SCHEMA }
)
const ctxBlock = ctx
  ? `\n\nAPP-CONTEXT (from the context pass — respect the legit_patterns; do not flag those):\npurpose: ${ctx.apparent_purpose}\naudience: ${ctx.audience}\nintended_aesthetic: ${ctx.intended_aesthetic}\nlegit_here: ${(ctx.legit_patterns || []).join('; ') || '(none noted)'}`
  : ''

// ---------------------------------------------------------------------------
// Phase: Lenses -> Verify  (pipeline: each lens's findings verify as soon as
// that lens completes — no barrier between reviewing and verifying)
// ---------------------------------------------------------------------------
const verifyFinding = (f, lensKey) =>
  agent(
    `${GROUND}${ctxBlock}\n\nYou are an adversarial SKEPTIC. A lens flagged this as AI slop:\n${JSON.stringify(f, null, 2)}\n\nYour job is to REFUTE it — argue it is an intentional, justified choice for THIS product, using the\ncatalog's "legit when" line for ${f.slop_id} and the app context. Read the cited screenshot and the\nfacts yourself; do not take the lens's word. If the refutation holds, set intentional=true (the finding\nis dropped). If it genuinely reads as unmotivated and uniform, set intentional=false and rate confidence\n(that it's slop) and risk (of the fix). Default toward intentional=true when truly unsure — a false flag\nis worse than a missed one. Copy findings (SLOP-08, SLOP-11) can be real but are never low-risk to auto-fix.`,
    { label: `verify:${lensKey}:${f.slop_id}`, phase: 'Verify', schema: VERDICT_SCHEMA }
  ).then(v => (v && !v.intentional ? { ...f, verdict: v } : null))

const perLens = await pipeline(
  LENSES,
  lens =>
    agent(
      `${GROUND}${ctxBlock}\n\nYou are the ${lens.key.toUpperCase()} lens. You hunt ONLY these tells: ${lens.tells}.\nFocus: ${lens.focus}\n\nRead every relevant screenshot AND the facts for each route. Report only what you can ground in BOTH a\nfact signal and what the image shows. Cite the actual numbers. Ignore every other category — other\nlenses cover those. Finding nothing is a valid, honest result.`,
      { label: `lens:${lens.key}`, phase: 'Lenses', schema: FINDINGS_SCHEMA }
    ).then(r => ({ lensKey: lens.key, findings: (r && r.findings) || [] })),
  res =>
    res && res.findings.length
      ? parallel(res.findings.map(f => () => verifyFinding(f, res.lensKey)))
      : []
)
let confirmed = perLens.flat().filter(Boolean)

// ---------------------------------------------------------------------------
// Phase: Critic — completeness over uncovered tells/pages, plus a false-flag check
// ---------------------------------------------------------------------------
phase('Critic')
const coveredIds = Array.from(new Set(confirmed.map(f => f.slop_id))).sort()
const critic = await agent(
  `${GROUND}${ctxBlock}\n\nYou are the COMPLETENESS CRITIC. The lenses confirmed findings for these tells: ${coveredIds.join(', ') || '(none)'}.\nRe-examine the screenshots and facts for: (a) any catalog tell (SLOP-01..18) NOT in that list that is\nclearly present and was missed; (b) any route that got little attention; (c) the inverse — soul-killing\ndefault-ness not captured by a single catalog row (a whole page where nothing looks chosen). Report NEW\nfindings only, same schema, each grounded in a fact signal + the image. Respect the legit_patterns. If\nnothing was missed, return an empty findings array — that's a good outcome.`,
  { label: 'critic', phase: 'Critic', schema: FINDINGS_SCHEMA }
)
const criticFindings = (critic && critic.findings) || []
if (criticFindings.length) {
  const extra = (await parallel(criticFindings.map(f => () => verifyFinding(f, 'critic')))).filter(Boolean)
  confirmed = confirmed.concat(extra)
}

// ---------------------------------------------------------------------------
// Phase: Synthesize
// ---------------------------------------------------------------------------
phase('Synthesize')
if (!confirmed.length) {
  return {
    runDir,
    findings: [],
    report: {
      overall_verdict: 'No AI-slop tells survived verification. Either the UI is made with intent, or every candidate was refuted as a legitimate choice for this product.',
      pages: (ctx?.routes || []).map(r => ({ route: r, verdict: 'deliberate', note: 'No confirmed findings.' })),
      ranked_findings: [],
    },
  }
}

const report = await agent(
  `${GROUND}${ctxBlock}\n\nYou are the SYNTHESIS pass. Here are the confirmed findings (each already survived adversarial\nverification and carries a verdict with confidence + risk + the refutation that failed):\n\n${JSON.stringify(confirmed, null, 2)}\n\nProduce the final report: a one-paragraph overall verdict naming the single biggest lever; a per-page\ndeliberate/mixed/slop verdict; and the findings ranked highest-leverage first. For each ranked finding\ncopy through its evidence/fix/source_hint, set confidence and risk from its verdict, put the surviving\nrefutation into "caveat", and set auto_applicable=true ONLY when confidence is HIGH, risk is low, and it\nis not a copy tell (SLOP-08, SLOP-11). Merge duplicates that name the same element across routes.`,
  { label: 'synthesize', phase: 'Synthesize', schema: REPORT_SCHEMA }
)

return { runDir, findings: confirmed, report: report || { overall_verdict: 'Synthesis failed; raw findings attached.', pages: [], ranked_findings: [] } }
