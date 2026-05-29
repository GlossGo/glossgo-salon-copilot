# Landing page (Cloudflare Pages)

Single-page marketing surface at:

- **Deployed**: <https://glossgo-copilot.pages.dev>
- **Custom domain target**: <https://copilot.glossgo.com> (pending DNS swap, see below)

## Deploy

```bash
CF=$(doppler secrets get CLOUDFLARE_API_TOKEN --project bilalsengul --config prd --plain)
CLOUDFLARE_API_TOKEN="$CF" CLOUDFLARE_ACCOUNT_ID=a01ee186bf9ebcbfc2e3e21e4c948737 \
  npx wrangler@latest pages deploy . --project-name=glossgo-copilot --branch=main
```

## One-time DNS swap on copilot.glossgo.com

The previous owner of this hostname is `softween-hub` (Workers route, AAAA `100::`).
To repurpose the subdomain for the landing:

1. Cloudflare Dashboard → BASE account → glossgo.com zone → DNS → Records.
2. **Delete** the AAAA record on `copilot` (`100::`, proxied).
3. **Add** a CNAME record:
   - Name: `copilot`
   - Target: `glossgo-copilot.pages.dev`
   - Proxy: ON (orange cloud)
4. Wait ~30 seconds for the CF Pages domain "initializing" → "active".

The Pages custom domain is already attached at the project side
(`copilot.glossgo.com`, status `pending`); deleting + recreating the DNS
record above is the only blocker.

## Why a CF token with DNS edit wasn't used

The `bilalsengul/prd/CLOUDFLARE_API_TOKEN` (`cfat_jSWj4ikQCqfPOiH...`) is
scope-limited to Access / Workers / Pages and was rejected with code 10000
on the DNS endpoint. A separate token with **Zone.DNS.Edit** on
glossgo.com is needed; check Doppler under a different project (memory
suggests a `cfut_DwktW` token elsewhere) or generate a new one at
<https://dash.cloudflare.com/profile/api-tokens>.
