export const meta = {
  name: 'source-crosscheck',
  description: 'Cross-check a bounded set of primary-source claims and preserve unsupported claims as unknown.',
}

const claims = Array.isArray(args?.claims) ? args.claims.slice(0, 6) : []
const checks = await pipeline(claims, claim => agent(`Verify this claim against the named primary source and exact version. Quote no more than necessary. Return VERIFIED, CONTRADICTED, or UNKNOWN with the source path or URL: ${claim}`, { label: String(claim).slice(0, 40) }))
return checks
