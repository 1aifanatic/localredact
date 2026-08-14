# Upstream research: `sam247/openredaction`

Research snapshot: upstream commit [`8141e5e8387a8ea4e2922524b168bbd74ae6d4b0`](https://github.com/sam247/openredaction/tree/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0), committed 2026-08-07. Sources below are pinned to that commit so the findings remain reproducible.

## Executive conclusion

OpenRedaction is a mature-looking **text PII detection and substitution toolkit**, not yet a true PDF-redaction product. Its strongest transferable idea is a deterministic pipeline of typed patterns, validators, context scoring, overlap resolution, and explicit redaction policies. Its least transferable parts are the sprawling JavaScript integration surface and enterprise subsystems.

Most importantly for this project:

- Upstream does **not** interpret free-form English instructions. Users select presets, flags, and pattern identifiers through constructors, a CLI, a browser dropdown, or JSON HTTP requests.
- Its PDF support extracts text and runs the same text detector. The result contains extracted and redacted strings, but it does not write a redacted PDF or remove content from PDF objects.
- Its core is local-by-default and regex-first, but some return values, reversible maps, learning files, server defaults, and optional webhooks create privacy responsibilities even without an AI provider.
- A much lighter Python product should keep the deterministic policy engine and safety checks, add a deliberately constrained local-English instruction compiler, and use a PDF library's **real redaction annotations plus apply step** rather than painting rectangles.

## What the upstream repository is

The root is a Bun/Turbo TypeScript monorepo targeting Node 20+, with eight package workspaces plus a Next.js site. The published surface is split into core, a compatibility package, CLI, React hooks, a built-in HTTP server, and Express/Hono/Elysia adapters; the workspace and toolchain are declared in the [root package manifest](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/package.json#L18-L63). At this snapshot, the repository contains:

| Layer | Responsibility | Relevant source |
| --- | --- | --- |
| `@openredaction/core` | Patterns, detection, validation, context scoring, masking, learning, document extraction, workers, audit, metrics, RBAC, reports | [core entry point](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/index.ts) |
| `@openredaction/core/lite` | Smaller facade that disables learning, NER, optimizer, audit, metrics, RBAC, multipass, reports, document, batch, and health features | [`lite.ts`](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/lite.ts#L1-L100) |
| `openredaction` | Backward-compatible aggregate package that re-exports core plus React, Express, and server integration paths | [compat README](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/compat/README.md#L1-L35) |
| CLI | Detect, scan, submit learning feedback, and import/export settings | [CLI README](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/cli/README.md#L1-L54) |
| HTTP/framework adapters | REST endpoints, middleware, framework-specific integration | [server README](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/server/README.md#L1-L51) |
| Site/playground | Documentation, marketing pages, and an in-browser lite detector | [playground implementation](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/site/app/playground/page.tsx#L413-L576) |

The center of gravity is `OpenRedaction`, a facade that merges a preset and user options, builds and priority-sorts the pattern list, then wires cache, placeholder, learning, optimization, audit, and the detection engine ([constructor](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/detector.ts#L41-L116)). The core package manifest has no mandatory runtime dependency block; PDF, DOCX, and OCR libraries are optional peers ([core manifest](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/package.json#L19-L81)). That split is a good precedent even though the total repository is broad.

## Public user experience

### Library

The primary UX is `npm install openredaction`, construct `OpenRedaction(options)`, and `await detect(text)`. The returned object exposes the original text, redacted text, typed detections, a placeholder-to-original `redactionMap`, and timing/count statistics ([public types](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/types.ts#L25-L93)). Options are structured rather than conversational: booleans for common entity families, category/pattern lists, custom regex objects, whitelists, presets, confidence thresholds, and redaction modes ([options](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/types.ts#L95-L165)).

### Command line

The CLI accepts literal text, not a document path, and uses switches such as `--preset hipaa`, `--patterns EMAIL,SSN`, and `--no-names`. It also exposes feedback/import/export commands for local learning ([CLI parser and help](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/cli/src/cli.ts#L6-L42), [option parsing](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/cli/src/cli.ts#L127-L164)). There is no command resembling `redact input.pdf --instruction "..."`.

### Browser playground

The playground dynamically loads the lite build and explicitly says input remains in the browser. Users select one of six presets, paste at most 5,000 characters, and view redacted text, entities, or JSON ([privacy/limit copy](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/site/app/playground/page.tsx#L421-L440), [input and preset controls](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/site/app/playground/page.tsx#L445-L576), [result tabs](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/site/app/playground/page.tsx#L600-L750)). A revealing comment says person names were intentionally omitted from demo samples because context-sensitive name matching can look broken ([sample rationale](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/site/app/playground/page.tsx#L52-L72)).

### HTTP API

The framework-free Node server exposes detect, redact, restore, pattern, audit, metrics, health, and docs endpoints ([route table](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/server/src/APIServer.ts#L398-L443)). Requests still contain structured `text`; they do not contain natural-language policy instructions or uploaded PDFs. `/api/detect` returns detections (including each matched raw value through the detection type), while `/api/redact` additionally returns `original` and `redacted` strings ([handlers](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/server/src/APIServer.ts#L446-L543)).

## How detection and redaction work

1. **Pattern assembly.** The repository eagerly combines personal, financial, government, contact, network, industry, international, and digital-identity arrays into `allPatterns` ([pattern registry](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/patterns/index.ts#L43-L80)). Users can reduce that set by exact pattern type or category and can append custom patterns ([pattern selection](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/detector/PatternManager.ts#L36-L76)). The README advertises 570+ patterns, but this should be understood as breadth, not proof of recall or precision ([claimed coverage and limitations](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/README.md#L13-L30)).

2. **Deterministic candidate generation.** Patterns are sorted by descending priority. Each compiled regex is run over the input, capped at 10,000 matches; higher-priority occupied ranges prevent lower-priority overlaps ([matching loop](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/detector/DetectionEngine.ts#L213-L301)). This is a simple and useful answer to conflicts such as a long identifier also matching a generic number.

3. **Validation and false-positive reduction.** A pattern can attach a validator. The engine then optionally applies a false-positive filter, local context analysis, proximity rules, a confidence threshold, and a whitelist ([candidate filtering](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/detector/DetectionEngine.ts#L303-L400)). Validators include real algorithms such as Luhn and IBAN mod-97, plus format/invalid-range checks for SSNs and other identifiers ([validator source](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/validators/index.ts#L5-L141)). Context scoring is deterministic: it infers coarse document type and adjusts scores using surrounding technical, business, medical, financial, and example terms ([context analyzer](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/context/ContextAnalyzer.ts#L111-L195), [confidence calculation](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/context/ContextAnalyzer.ts#L198-L260)).

4. **Optional local NER.** When enabled, the engine tries to load `compromise` and adds people, organizations, places, dates, money, email, phone, and URL candidates with fixed base confidences. If the dependency is absent it silently falls back to regex ([NER loader](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/ml/NERDetector.ts#L52-L85), [entity extraction](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/ml/NERDetector.ts#L87-L255)). This is local NLP, not an agent or hosted model.

5. **Text substitution.** Detections receive placeholders, the detector replaces every case-insensitive occurrence of each detected value, and it records a reversible map ([redaction loop](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/detector/DetectionEngine.ts#L145-L172)). Modes are placeholder, mask-middle, mask-all, format-preserving, and deterministic fake-data replacement ([strategy implementations](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/utils/redaction-strategies.ts#L8-L195)). Deterministic placeholder IDs use an unkeyed 32-bit FNV-1a-derived value reduced to four digits ([hash implementation](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/utils/hash.ts#L5-L28)). These IDs are for consistency, not cryptographic anonymization.

6. **Document extraction.** `detectDocument()` reads a buffer, extracts text and metadata, calls the same text detector, and returns the extracted text plus detection result ([facade implementation](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/detector.ts#L321-L367)). PDF uses `pdf-parse`; DOCX uses Mammoth; images use Tesseract; TXT/JSON/CSV have local paths, and XLSX has a separate processor ([document dispatcher](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/document/DocumentProcessor.ts#L16-L94)). Despite `pages` and `enableOCR` appearing in the public options, PDF page selection is explicitly left as a future enhancement and there is no scanned-PDF OCR fallback in the PDF branch ([PDF extractor](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/document/DocumentProcessor.ts#L279-L311), [document options/result](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/document/types.ts#L52-L84)).

## Strengths worth retaining

- **Local, deterministic default.** The primary detector needs no remote inference, is testable offline, and produces explainable typed matches.
- **Layered precision.** Regex gives candidate recall; checksums and structural validators cheaply reject impossible values; surrounding labels adjust ambiguous values. This is the right basic architecture for a no-AI service.
- **Explicit policy.** Presets, category filters, exact pattern filters, allowlists, custom patterns, confidence thresholds, and modes make behavior inspectable and reproducible.
- **Priority and overlap handling.** A normalized match representation (`type`, raw span, page/text position, confidence, severity) followed by one conflict-resolution step is cleaner than performing destructive edits detector-by-detector.
- **Reversible and irreversible modes are separated conceptually.** Even though a PDF product should default to irreversible removal, it is useful to distinguish black-box removal, masking, pseudonymization, and reversible tokenization.
- **A lite entry already validates the “small core, optional extras” direction.** The lite facade intentionally disables the enterprise subsystems while preserving detection and restoration ([lite constructor](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/lite.ts#L36-L100)).
- **Quality automation exists.** Core tests cover detectors, validators, false positives, context, modes, performance, streaming, and patterns, and CI runs lint/test/build plus packed-consumer smoke tests on Node 20/22/24/26 ([core test tree](https://github.com/sam247/openredaction/tree/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/tests), [CI workflow](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/.github/workflows/ci.yml)).

## Heavyweight or unsuitable parts for the Python product

At the pinned snapshot, the core TypeScript source alone is approximately 0.84 MB across 102 files; pattern source accounts for about 0.38 MB across 41 files. The repository additionally carries eight packages, a 300-file site tree, framework adapters, release tooling, and enterprise-style modules. Those are reasonable for an ecosystem, but counterproductive for a single-purpose `pip install` tool.

Specific pieces to avoid or narrow:

- **Do not port all 570+ rules on day one.** Large pattern libraries create maintenance and false-positive costs. Start with a small evidence-backed set for common instructions: email, phone, SSN/national ID variants chosen by locale, card number + Luhn, bank/account identifiers, IP address, URL credentials, and exact literals. Add pattern packs as data files or optional extras.
- **Do not port tenancy, RBAC, webhooks, Prometheus, persistent audit databases, reports, workers, React hooks, or three web-framework adapters.** A library + CLI is sufficient; a loopback-only HTTP service can be an optional extra.
- **Do not mistake text extraction for PDF redaction.** Upstream never maps match offsets back to PDF coordinates or calls an operation that deletes page content. Returning a redacted string alongside the unchanged original PDF does not satisfy the requested outcome.
- **Do not make generic person-name regex a default promise.** Upstream's own playground avoids names because this looks unreliable. Support exact quoted names and strong labeled contexts first; keep broad local NER optional.
- **Do not call the upstream regex timeout a hard sandbox.** `safeExec()` measures elapsed time only *after* JavaScript's blocking `regex.exec()` returns, so it cannot interrupt an in-flight catastrophic expression; its static unsafe-pattern check is intentionally described as a basic heuristic ([implementation and caveat](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/utils/safe-regex.ts#L25-L59), [static analysis](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/utils/safe-regex.ts#L114-L168)). In Python, built-in rules should be audited; user regex should be length-limited and executed through an engine/process with a real timeout.
- **Avoid global value replacement as the primary edit model.** Upstream detects spans but then globally replaces the detected value case-insensitively. A PDF implementation should redact the resolved spans/rectangles only, preserving page-scoped exceptions and reducing accidental over-redaction.

## Privacy and security implications

“Local” is necessary but not sufficient. The upstream core does not upload input by default, yet sensitive material survives in several forms:

- Every `DetectionResult` retains `original`, each detection's raw `value`, and a reversible `redactionMap` ([result type](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/types.ts#L25-L83)). Serializing this result can undo the privacy benefit.
- Learning is enabled by default by the full facade. Explicit feedback writes false-positive values, contexts, and false-negative examples in plaintext to `.openredaction/learnings.json` ([default activation](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/detector.ts#L62-L73), [learning store schema/write](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/learning/LocalLearningStore.ts#L30-L60), [feedback persistence](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/learning/LocalLearningStore.ts#L91-L175)).
- Deterministic unkeyed placeholders permit equality linkage across documents and have only 10,000 possible IDs per type. They are helpful for readability, not safe pseudonymization.
- Optional webhooks deliberately post event data to arbitrary URLs ([event/config types](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/core/src/webhooks/WebhookManager.ts#L21-L74)). A strictly local product should omit them from the core.
- The optional HTTP server defaults to `0.0.0.0`, CORS `*`, and no API key unless supplied ([server defaults](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/server/src/APIServer.ts#L15-L45), [constructor values](https://github.com/sam247/openredaction/blob/8141e5e8387a8ea4e2922524b168bbd74ae6d4b0/packages/server/src/APIServer.ts#L111-L131)). A local Python server must instead default to `127.0.0.1`, refuse non-loopback binding without an explicit unsafe flag, and never echo original text unless requested.

For the new package, safe defaults should be: no telemetry; no socket use; no persistent learning; no reversible map; output to a new path; atomic save; raw values absent from logs/manifests; metadata and embedded-file policy explicit; and a verification pass after saving.

## Recommended lightweight Python shape

### One small, deep public interface

```bash
pip install localredact
localredact input.pdf \
  --instruction "Redact email addresses, phone numbers, and SSNs on every page except support@example.com" \
  --output input.redacted.pdf

# Always available before modification
localredact plan input.pdf --instruction "Redact card numbers and the patient named 'Jane Doe'"
```

```python
from localredact import redact

report = redact(
    "input.pdf",
    "Redact email addresses and SSNs, but keep support@example.com",
    output="input.redacted.pdf",
)
```

The first install should have one substantive runtime dependency: PyMuPDF. It can extract text with location information, search page text, create redaction annotations, and apply them. The crucial distinction is that [`Page.add_redact_annot()`](https://pymupdf.readthedocs.io/en/latest/page.html#Page.add_redact_annot) marks regions and [`Page.apply_redactions()`](https://pymupdf.readthedocs.io/en/latest/page.html#Page.apply_redactions) performs content removal; the service must do both. PyMuPDF's [`Page.get_text()`](https://pymupdf.readthedocs.io/en/latest/page.html#Page.get_text) provides the basis for mapping extracted tokens back to rectangles. OCR should be a separately installed extra because PyMuPDF's own [OCR recipe](https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html) depends on Tesseract and is orders of magnitude slower than normal text extraction.

### Internal pipeline

```text
English instruction
    -> normalize + parse into typed RedactionPlan
PDF -> extract words/spans with page coordinates
    -> selected detectors -> validate -> score
    -> apply allow/deny literals and page scopes
    -> resolve overlapping Match objects
    -> dry-run plan/report
    -> add redaction annotations -> apply redactions -> atomic save
    -> reopen output and verify removed text is no longer extractable/searchable
```

Use a few deep modules rather than mirroring upstream's subsystems:

| Module | Narrow responsibility |
| --- | --- |
| `intent.py` | Compile constrained English into a typed, serializable `RedactionPlan`; report ambiguity instead of guessing |
| `patterns.py` | Small declarative rule registry: aliases, regex, validator, priority, default confidence |
| `detect.py` | Run selected rules over page text, emit immutable matches, resolve overlap |
| `pdf.py` | Extract coordinate-aware text, turn matches into rectangles, apply true PDF redactions, save safely |
| `verify.py` | Reopen output, search for detected literals, detect unapplied annotations, produce raw-value-free report |
| `cli.py` | File-oriented CLI plus `plan`/dry-run UX; optional loopback server can be a later extra |

### “Understand English” without AI

Do not simulate an unconstrained language model. Use a controlled-natural-language compiler that feels conversational for the intended domain:

- normalize verbs (`redact`, `remove`, `hide`, `black out`, `mask`);
- map aliases (`emails`, `email addresses`, `e-mail` -> `EMAIL`; `social security numbers`, `SSNs` -> `US_SSN`);
- parse Boolean connectors and scopes (`and`, `only`, `except`, `but keep`, `on pages 2-4`, `after the label ...`);
- treat quoted phrases as exact literals;
- map domain bundles (`HIPAA identifiers`, `contact details`, `financial identifiers`) to versioned local presets;
- return the compiled plan in `plan` mode so the user can see exactly what was understood;
- reject unknown entity nouns or ambiguous negation with a useful message and list of supported phrases.

This is local, fast, auditable, and much safer than silently pretending to understand arbitrary instructions. The parser output, not the English string, should be the contract consumed by detection.

### Redaction policy and output safety

- Default PDF mode should be irreversible black-box redaction. Text masking/pseudonymization is a separate mode because it may not fit the original glyph geometry and is not equivalent to removal.
- Use typed matches with `page`, `rects`, `kind`, `confidence`, `rule_id`, and a keyed digest of the value. Keep raw values only in short-lived memory.
- Never put raw matches in normal logs, JSON reports, exceptions, or filenames. A `--reveal-values` diagnostic flag should be explicit and visually warned.
- Never overwrite the source by default. Save to a sibling temporary file, complete verification, then atomically rename to the requested output.
- Reopen the produced PDF and search/extract for every removed literal. Verification cannot prove semantic completeness, but it does catch unapplied annotations and many coordinate/edit failures.
- Report scanned/image-only pages explicitly. The base package should fail closed or mark them unprocessed; an `[ocr]` extra may invoke a locally installed Tesseract path with no automatic cloud fallback.
- Add fixtures that prove content is removed from extraction, not merely covered visually. Include rotated text, split text runs, repeated values, page-scoped exceptions, metadata, annotations, and image-only pages.

## Transfer decision table

| Upstream concept | Decision for lightweight Python service | Reason |
| --- | --- | --- |
| Regex-first local detection | Keep | Fast, deterministic, offline |
| Validators/checksums | Keep | Large precision gain for little complexity |
| Context labels and confidence | Keep, simplify | Useful for ambiguous IDs and names without a model |
| Priority + overlap resolution | Keep | Essential when rules collide |
| Presets and exact allowlist | Keep | Natural target for English instruction compilation |
| Deterministic placeholder map | Optional text mode only | Reversible/linkable and irrelevant to irreversible PDF boxes |
| Generic name regex | Do not enable by default | High ambiguity; prefer exact literals/labeled fields or optional local NLP |
| 570+ eagerly imported patterns | Replace with small versioned packs | Lower install/maintenance cost and clearer quality claims |
| Learning store | Omit from MVP | Persists sensitive examples and complicates determinism |
| PDF text extraction only | Replace | Must map detections to page rectangles and apply real redactions |
| OCR | Optional extra | Native dependency and high CPU/startup cost |
| REST/framework ecosystem | Defer; loopback-only extra | CLI/library covers the primary local workflow |
| Tenancy/RBAC/webhooks/metrics/reports | Omit | Not required for a personal/local redaction primitive |

## MVP completion bar suggested by the research

1. A clean environment can `pip install` the wheel and run one file-oriented command.
2. The command accepts a PDF, simple English instruction, and optional output path; `plan` shows the parsed policy and counts before writing.
3. All processing works with network disabled and has no model download, telemetry, API key, or agent integration.
4. At least email, phone, US SSN, credit card + Luhn, IP, exact quoted literals, allowlisted exceptions, and page scopes work on born-digital PDFs.
5. The output PDF preserves page count/layout and detected content is removed from the PDF content stream through applied redactions.
6. A verification pass reopens the output and fails the operation if selected raw literals remain searchable/extractable.
7. Logs and default reports contain types, counts, pages, coordinates, rule versions, and value digests—but no original document text or raw PII.
8. Image-only pages are never silently declared clean; they produce a clear local-OCR-required status.
9. Tests cover instruction parsing, validators, false positives, coordinate mapping, true removal, exceptions, and offline operation.

That product would borrow OpenRedaction's best design lesson—layer cheap, explainable techniques—while solving the two requirements upstream does not: **English-to-policy compilation** and **actual local PDF content removal**.
