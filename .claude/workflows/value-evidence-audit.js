export const meta = {
  name: 'value-evidence-audit',
  description: 'Adversarially audit a milestone value-evidence file against its predeclared contract.',
}

const angles = [
  'Check whether the metric and threshold were predeclared and not changed after results.',
  'Try to falsify each required condition from raw artifacts and commands.',
  'Check whether the claimed user outcome is materially large, not merely technically nonzero.',
  'Check for fabricated adoption, customer, maintainer, or payment claims.',
]
const reviews = await pipeline(angles, angle => agent(angle, { label: angle.slice(0, 40) }))
return await agent(`Synthesize only independently supported conclusions. Return PASS only if every required condition survives adversarial review. Otherwise return REDESIGN or EXTERNAL_EVIDENCE_REQUIRED.\n${JSON.stringify(reviews)}`)
