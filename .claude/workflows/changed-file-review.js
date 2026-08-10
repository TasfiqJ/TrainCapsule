export const meta = {
  name: 'changed-file-review',
  description: 'Review each changed file independently, then rank only evidence-backed findings.',
}

const files = await agent('List changed tracked and untracked files relative to the supplied base SHA. Return only repository-relative files.', {
  schema: { type: 'object', required: ['files'], properties: { files: { type: 'array', items: { type: 'string' } } } },
})

const reviews = await pipeline(files.files.slice(0, 6), file =>
  agent(`Review ${file} for correctness, security, test weakening, fake integration, and evidence laundering. Cite exact lines and return no finding when none is substantiated.`, { label: file })
)

return await agent(`Deduplicate and rank these independent reviews. Discard speculative findings. Require a concrete reproduction or exact code path for every blocking claim:\n${JSON.stringify(reviews)}`)
