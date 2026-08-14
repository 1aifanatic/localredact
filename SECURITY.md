# Security policy

## Supported versions

The latest `0.1.x` release receives security fixes. Pre-release and older builds
are unsupported; upgrade before reporting behavior that may already be fixed.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability or attach a sensitive
document. Use
[GitHub private vulnerability reporting](https://github.com/1aifanatic/localredact/security/advisories/new)
to contact the maintainer privately. Include a minimal synthetic reproducer,
affected version, operating system, Python version, and expected versus observed
behavior. Remove all real personal or confidential data.

Security-sensitive reports include incomplete PDF content removal, sensitive data
appearing in logs or reports, path or file-overwrite vulnerabilities, unsafe
network-service defaults, and malicious-PDF crashes with a plausible security
impact.

The maintainer aims to acknowledge reports within seven days. Coordinated public
disclosure should wait until a fix or mitigation is available.

## Scope and limitations

LocalRedact is best-effort alpha software, not a compliance certification.
Unusual encodings, handwriting, weak OCR, vector outlines, or novel identifiers
can evade detection. High-stakes outputs require human visual review.
