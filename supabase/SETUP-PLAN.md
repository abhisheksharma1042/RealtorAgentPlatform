# Supabase Branching + dotenvx Setup Plan

Date: 2026-07-15
Scope: Prepare the `supabase/` directory for Git-based branch configuration and encrypted secret management.

## 1) Desired end state

- Supabase branching configuration is managed as code from `supabase/config.toml`.
- Persistent branch-specific overrides are defined in `[remotes.<branch>]` blocks with valid `project_id` values.
- Secret values are managed with dotenvx encrypted files for preview/production flows.
- Sensitive local key material is never committed.
- CI and developer workflow can safely push config changes from Git and have Supabase apply them.

## 2) Current state snapshot

- `supabase/` currently contains only `.gitkeep`.
- Root `.gitignore` currently ignores `.env` and `.env.local`, but does not explicitly ignore `supabase/.env.keys`.

## 3) File layout to create and manage

Under `supabase/`:

- `config.toml`
  - Supabase config as code for default branch behavior and remote-specific overrides.
- `.env.preview`
  - Encrypted values used for branch/preview deployments.
  - Committed to Git.
- `.env.production`
  - Encrypted values used for production branch config.
  - Committed to Git.
- `.env.local`
  - Local-only developer secrets and overrides.
  - Not committed.
- `.env.keys`
  - Decryption keys for encrypted dotenvx files.
  - Not committed.

Optional:

- `.env`
  - Shared encrypted values if you want one file for multiple environments.

## 4) Implementation phases

### Phase A: Bootstrap Supabase config

1. Run `supabase init` at repo root (if `supabase/config.toml` does not exist yet).
2. Confirm `supabase/config.toml` is generated.
3. Keep defaults minimal first; avoid environment-specific values until remotes are known.

Acceptance criteria:

- `supabase/config.toml` exists and parses.

### Phase B: Map Git branches to Supabase remotes

1. List branch remotes:
   - `supabase --experimental branches list`
2. Since only one persistent branch exists today, target `production` only.
3. Add remote blocks to `config.toml`:
  - `[remotes.production]`
   - `project_id = "<BRANCH PROJECT ID>"`
4. Add remote-specific overrides only where needed (for example seed paths or provider settings).

Acceptance criteria:

- Every persistent Git branch with managed config has a matching `[remotes.<name>]` block with a valid project id.

### Phase C: Establish dotenvx encrypted secret workflow

1. Create encrypted preview values using dotenvx:
   - `npx @dotenvx/dotenvx set <KEY> "<VALUE>" -f supabase/.env.preview`
2. Create encrypted production values similarly in `supabase/.env.production`.
3. Keep machine-local keys in `supabase/.env.keys`.
4. Push decryption keys to Supabase secrets:
   - `npx supabase secrets set --env-file supabase/.env.keys`

Acceptance criteria:

- `supabase/.env.preview` and `supabase/.env.production` contain encrypted values.
- `supabase/.env.keys` is present locally and uploaded to Supabase secrets.

### Phase D: Wire secrets into config.toml safely

1. Use `env(...)` references for most values, especially non-secret or unsupported encrypted fields.
2. Use `encrypted:...` only on supported secret fields (for example `auth.external.*.secret`).
3. For your GitHub integration, prefer:

```toml
[auth.external.github]
enabled = true
client_id = "env(SUPABASE_AUTH_EXTERNAL_GITHUB_CLIENT_ID)"
secret = "env(SUPABASE_AUTH_EXTERNAL_GITHUB_SECRET)"
```

4. If remote-specific OAuth differs by environment, place provider config inside each `[remotes.<branch>.auth.external.github]` block.

Acceptance criteria:

- `config.toml` uses env/encrypted patterns that match Supabase-supported fields.
- No plaintext secrets remain in tracked files.

### Phase E: Git hygiene and guardrails

1. Update root `.gitignore` to include:
   - `supabase/.env.keys`
   - `supabase/.env.local`
2. Keep `supabase/.env.preview` and `supabase/.env.production` tracked.
3. Add a quick pre-commit check (manual or script) to block plaintext secret patterns in `supabase/*.env*` and `supabase/config.toml`.

Acceptance criteria:

- Local secret key files are ignored by git.
- Encrypted environment files remain tracked.

### Phase F: Validate branch executor behavior

1. Open a small PR changing a harmless config value in `config.toml`.
2. Merge into target branch and confirm Supabase integration applies config.
3. Verify expected behavior in the branch dashboard (auth provider/setting visible and active).
4. Re-run branch list and ensure remotes still map correctly.

Acceptance criteria:

- Config updates from Git are detected and applied to matching Supabase branches.

## 5) Recommended first pass scope

Do this first:

- `config.toml` creation.
- `[remotes.production]` mapping.
- GitHub OAuth via `env(...)` values.
- dotenvx encryption in `.env.preview`.
- `.gitignore` protection for `.env.keys` and `.env.local`.

Then expand:

- Add any additional branch remotes only when new persistent branches are created.
- Add branch-specific overrides only where needed.

## 6) Risks and controls

- Risk: `project_id` mismatch in remotes.
  - Control: Copy IDs directly from `supabase --experimental branches list`.
- Risk: Encrypted value used in unsupported field.
  - Control: Use `env(...)` unless field is explicitly supported for `encrypted:`.
- Risk: Leaking decryption keys.
  - Control: Never commit `supabase/.env.keys`; keep gitignore entry enforced.
- Risk: Local works but branch executor fails.
  - Control: Validate with a small PR before broader config rollout.

## 7) Execution owner checklist

- [x] Initialize Supabase config (`supabase init`)
- [x] Add remote mappings in `config.toml` (production project ref populated)
- [x] Generate encrypted `.env.preview`
- [x] Generate encrypted `.env.production`
- [x] Upload `.env.keys` via `supabase secrets set`
- [x] Update `.gitignore` for secret key files
- [ ] Run PR-based integration validation
- [x] Document branch-id mapping for team (`main -> cchkagosciauviahicwt`, `production -> cchkagosciauviahicwt`)

## Source used

- Supabase docs: Branching configuration and dotenvx workflow
  - https://supabase.com/docs/guides/deployment/branching/configuration#using-dotenvx-for-git-based-workflow

## 8) Final implementation notes

- Supabase secrets reject custom names starting with `SUPABASE_` for user-defined entries.
- GitHub OAuth secrets are stored as `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`.
- `config.toml` is wired to those names via:
  - `auth.external.github.client_id = "env(GITHUB_CLIENT_ID)"`
  - `auth.external.github.secret = "env(GITHUB_CLIENT_SECRET)"`
