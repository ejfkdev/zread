# zread — Code Review & Feature Plan

_Review of `zread/__init__.py` (4,250 lines), Docker/compose assets, CI workflow, and locales as of `b4a218a` (post-standalone refactor). Line numbers refer to `zread/__init__.py`._

---

## 1. Bugs (confirmed, by severity)

### High

**H1. MCP stdio protocol corruption — error messages printed to stdout**
`_gh_api_get` (lines 1573, 1578–1584), `_gh_fetch_raw` (1613–1617) and `_github_fetch_file_meta` (1878) call `print(...)` on error paths. In `zread mcp stdio` mode, stdout **is** the JSON-RPC channel, so any GitHub error (rate limit, network failure, 5xx) during a tool call writes a bare text line into the protocol stream and can break the client session. The logging setup in `_run_mcp_server` (4205–4218) only silences `logging`, not these `print()`s.
*Fix:* route all diagnostics through `logging` / `print(..., file=sys.stderr)`.

**H2. MCP `get_repo_info` returns a bogus success for nonexistent repos**
`_get_repo_info` → `_github_repo_metadata` returns `{"_error": "not_found"}` (1849), which is truthy, so `get_repo_info` (2155–2158) happily passes it to `_clean_repo_info` and returns `{"url": "https://github.com/None/None", "name": "", ...}` instead of an error. The CLI (`cmd_stat`, 3648) checks `_error`; the MCP tool does not.
*Fix:* check `result.get("_error")` before cleaning.

**H3. Empty results are reported as failures in MCP tools**
Several tools use `if result:` where `result` can legitimately be empty:
- `search_repos` (2109–2112): a query with 0 hits returns `{"error": "search failed"}` instead of `{"repos": []}`.
- `get_trending` (2130–2133): an empty group list becomes an error.
- `read_doc` (2003–2006): a legitimately empty file (`""`) is reported as a fetch failure.
*Fix:* distinguish `None` (failure) from empty (success) — `if result is not None:`.

**H4. `llms.txt` export generates broken local links**
`_generate_llms_txt` links to `./{slug}.md` (4009, 4023), but `slug` is the full file path **including its extension** (files are saved as `output_dir / slug` in `_fetch_page_async`, 3712). Every link points at `README.md.md`, `docs/guide.md.md`, etc.
*Fix:* link to `./{slug}` as saved.

**H5. Hardcoded `blob/main` produces broken links for non-`main` repos**
`_process_markdown_links` rewrites file links to `https://github.com/{repo}/blob/main/{path}` (3132) while every other URL builder uses `blob/HEAD` (`_page_url`, 3124). Repos whose default branch is `master` (or anything else) get 404 links in rendered docs.
*Fix:* use `HEAD` consistently.

### Medium

**M1. `zread mcp <typo>` exits silently**
`_run_mcp_server` (4192–4240) handles `stdio` / `sse` / `http`; any other transport string prints "started" to stderr and then falls through and exits 0 with no server and no error.
*Fix:* validate transport in `cmd_mcp` and exit non-zero with a message.

**M2. MCP `get_trending(weeks)` always burns 4 search-API calls and caps at 4**
`get_trending` (2130) calls `get_trending_repos(lang)` → `_github_trending(lang)` with the default `weeks=4`, then slices `[:weeks]`. `weeks=1` wastes 3 unauthenticated search requests (rate limit: 10/min anonymous); `weeks=5+` silently returns only 4.
*Fix:* pass `weeks` through.

**M3. HTTP retries have no backoff**
`_retry_sync_request` / `_retry_async_request` (214–251) retry up to 3× **immediately**. For 429 (rate limit) this is counterproductive and can extend the ban.
*Fix:* exponential backoff, honor `Retry-After` / `x-ratelimit-reset`.

**M4. Truncated git trees are silently accepted**
`_gh_doc_tree` (1657–1690) uses `GET /git/trees/{branch}?recursive=1` but never checks the `truncated: true` flag GitHub sets for very large repos — the outline/search quietly misses files with no warning.
*Fix:* detect `truncated` and warn (or fall back to the Contents API per directory).

**M5. Trailing slash / `.git` suffix break repo parsing**
`parse_repo_url("owner/repo/")` yields `file_path=""` (not `None`), so `cmd_cat` skips doc mode and then errors on the empty path instead of showing the README. `owner/repo.git` produces repo `repo.git`. Also, `blob/<ref>` URLs (1382) parse but **discard the ref** — a link to a tag/branch silently reads HEAD instead.
*Fix:* `rstrip("/")`, strip `.git`, and carry `ref` through the result dict.

**M6. Plain-mode trending numbering is wrong**
`_format_trending_plain` (759) continues numbering across week groups with `start_idx=len(lines) // 5 + 1`, but items emit 2–4 lines each, so indices drift arbitrarily.
*Fix:* track a running item counter.

**M7. Unbounded process-lifetime caches in the shared server**
`_GH_REPO_CACHE`, `_GH_TREE_CACHE` (1544–1545) and `_IMAGE_CACHE` (86) grow forever and never expire. For the Docker "company-wide" deployment this means unbounded memory growth **and** permanently stale repo metadata/outlines (a repo indexed once never refreshes until restart).
*Fix:* small TTL-LRU (e.g. 15 min, few hundred entries).

**M8. Rich private-API usage**
`_run_with_cli_status` calls `status._live.start(refresh=True)` (2461) instead of the public `status.start()` — liable to break on a Rich upgrade.

**M9. i18n fallback and hardcoded Chinese leak into English mode**
- Fallback locale is `zh` (1268): any missing EN key shows Chinese to English users. It should fall back to `en`.
- Hardcoded Chinese bypassing i18n: `weekly_trending_resource` error (2216), export error `"无法获取文档大纲"` (3744), `parse_repo_url`'s `ValueError` message (1407–1409).

**M10. Stale zread.ai-era artifacts survive the standalone refactor**
These are not cosmetic — MCP tool docstrings are the tool descriptions LLM agents read:
- `discover_repo` (2065) and `get_repo_info` (2139–2143) docstrings still describe "Zread.ai" indexing and `status: progress/inactive` states that can no longer occur (status is always `"success"`, 1853).
- `_clean_repo_info`'s `repo_id` / `wiki_id` / `_submitted` / `_refreshed` handling (911–923) and `_format_single_repo_info`'s "未收录 / 索引中" branches (690–697) are dead.
- `_parse_cat_args` has a dead `source == "zread"` branch (2899) — `parse_repo_url` never returns that source.
- `CLI_COMMANDS` (4138–4149) lists `outline/page/search/trending/discover/ask/info/export` — none exist (actual: `ls/cat/find/top/rand/stat/cp`) — and the list is referenced nowhere.
- `run_tests` (1915) is unreachable from the CLI.

### Low

- `documentation_catalog_resource` (2206) is annotated `-> str` but returns a dict.
- `_parse_address` (4155): `int(port_str)` can raise an uncaught `ValueError` (`zread mcp http :abc` → traceback); no IPv6 support.
- `_preload_images_sync` (536): in an already-running event loop it fires `create_task` without awaiting, so images render as raw markdown anyway.
- `_cat_github_file` (3351) is an unused legacy wrapper.
- `weekly_trending_resource` returns the raw internal structure, not the `_clean_*` shape the tools use.

---

## 2. Structural / potential problems

1. **No tests, no test CI.** The only workflow is release-publish. `run_tests` is a network-dependent smoke test not wired to anything. Any of the bugs above would have been caught by a small mocked suite.
2. **Single 4,250-line module** mixing config, HTTP layer, GitHub data layer, Rich rendering, CLI, MCP server, and export. Hard to review, impossible to test in isolation.
3. **Anonymous rate limits are the product's main failure mode** (60 core req/h, 10 search req/min) and there is no caching between processes, no conditional requests (ETags), and no user-visible remaining-quota signal — just an error string.
4. **Docker healthcheck** only proves the TCP port accepts connections, not that MCP responds; acceptable but worth noting.
5. **`GITHUB_TOKEN` in a world-readable config file** (`~/.config/zread/zread.toml`) — worth a note in docs to `chmod 600`, and the file is read without permission checks.

---

## 3. Feature plan

### Phase 0 — Hardening (prerequisite, ~small)
1. Fix all High/Medium bugs above (H1–H5, M1–M10).
2. Split `zread/__init__.py` into a package: `config.py`, `http.py` (wrapped clients + retry/backoff), `github.py` (data layer), `render.py` (Rich/plain/JSON formatting), `cli.py`, `mcp_server.py`, `export.py`. Keep `zread/__init__.py` re-exporting the public API so `zread:main` and imports stay stable.
3. Add `pytest` + `respx` (httpx mocking) suite covering: `parse_repo_url` edge cases, retry/backoff, empty-result vs failure paths of every MCP tool, outline/search, export link generation.
4. Add a CI workflow: `ruff` + `pytest` on 3.10–3.13, run on PRs; wire the existing smoke test as an optional nightly job.

### Phase 1 — Rate-limit resilience & refs (highest user value)
1. **Conditional-request disk cache**: cache GitHub API responses under `~/.cache/zread/` keyed by URL with stored ETags; a 304 costs no core quota. This multiplies effective anonymous quota and makes the shared Docker server viable without a token.
2. **Ref support end-to-end**: `zread cat owner/repo@v1.2 file`, `--ref` option, and a `ref` argument on `read_doc` / `read_source_file` / `get_doc_outline` MCP tools. `parse_repo_url` already sees the ref in `blob/<ref>/` URLs — stop discarding it (M5).
3. **`zread limits`** command + `get_rate_limit` MCP tool: show remaining core/search quota and reset time, and whether a token is active.
4. Honor `Retry-After` and surface a clear "rate-limited until HH:MM, set GITHUB_TOKEN" message everywhere.

### Phase 2 — Deeper repo reading
1. **Full file tree**: `zread tree owner/repo [path]` + `list_repo_files` MCP tool (Contents/trees API), so agents can navigate beyond Markdown docs.
2. **Code search in repo**: `zread find owner/repo <query> --code` + `search_code` MCP tool using GitHub's code-search API (token-gated; fall back to doc grep without one).
3. **Releases & tags**: `zread releases owner/repo` + `get_releases` tool — changelog access is a top agent use case.
4. **Doc-content cache for search**: `_github_search_docs` re-downloads up to 30 files per query; cache fetched blobs (ties into Phase 1 cache).
5. **Token-aware output for MCP**: optional `max_bytes`/pagination on `read_doc`/`read_source_file` so huge files don't blow agent context windows.

### Phase 3 — Enterprise & export polish
1. **GitHub Enterprise support**: `ZREAD_GITHUB_API_URL` / `ZREAD_GITHUB_RAW_URL` env + config keys (currently hardcoded constants, 164–165).
2. **Export improvements** (`zread cp`): fix llms.txt links (H4), add `--include-source` to bundle code files, front-matter per exported page, and an `--llms-only` mode.
3. **Shared-server ops**: `/healthz` HTTP endpoint for a real healthcheck, optional Prometheus-style counters (requests, cache hits, rate-limit rejections), structured logs.
4. **Config command**: `zread config set lang en` / `config set github_token ...` (with `chmod 600`) instead of hand-editing TOML.

### Suggested sequencing
Phase 0 items 1–2 first (bug fixes land cleanly before the split, or fold H/M fixes into the split PRs one module at a time). Phase 1.1 (ETag cache) is the single highest-leverage feature — it de-risks every other feature that adds API calls.

---

*Full details, line references and reproduction notes are in section 1; each High/Medium item is sized as an independent, testable PR.*
