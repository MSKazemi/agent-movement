"""Issue #21: no committed receipt artifact may look like a credential to a secret scanner.

Two checks over the files the movement-receipts feature owns:

1. ``SecretScannerRuleSubsetTests`` (stdlib, always runs): a documented subset of the
   gitleaks v8.30.1 default rules (``config/gitleaks.toml``, commit at tag v8.30.1),
   copied verbatim. It is deliberately STRICTER than gitleaks: no keyword pre-filter, no
   stopword allowlist, ``$`` matches at every line end, and the entropy cut-off is ``>=``.
2. ``GitleaksBinaryTests``: the full default rule set via the real ``gitleaks`` binary
   (on PATH, or named by ``$GITLEAKS``). It skips when the binary is absent; the CI
   extras job installs a pinned, checksum-verified gitleaks so it never skips there.
"""

import base64
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from agent_movement import receipt_fixtures, receipts

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "movement-receipts"
# Every committed file the movement-receipts feature owns.
OWNED = sorted([*(p for p in FIXTURES.rglob("*") if p.is_file()),
                ROOT / "src" / "agent_movement" / "receipts.py",
                ROOT / "src" / "agent_movement" / "receipt_fixtures.py",
                ROOT / "src" / "agent_movement" / "jcs.py",
                ROOT / "src" / "agent_movement" / "live_receipts.py",
                ROOT / "tests" / "test_movement_receipts.py",
                ROOT / "tests" / "test_live_receipts.py",
                Path(__file__).resolve(),
                ROOT / "docs" / "movement-receipts.md"])

# (rule id, entropy threshold or None, regex): verbatim from gitleaks v8.30.1 config/gitleaks.toml.
GITLEAKS_RULES = (
    ("generic-api-key", 3.5, r'''(?i)[\w.-]{0,50}?(?:access|auth|(?-i:[Aa]pi|API)|credential|creds|key|passw(?:or)?d|secret|token)(?:[ \t\w.-]{0,20})[\s'"]{0,3}(?:=|>|:{1,3}=|\|\||:|=>|\?=|,)[\x60'"\s=]{0,5}([\w.=-]{10,150}|[a-z0-9][a-z0-9+/]{11,}={0,3})(?:[\x60'"\s;]|\\[nr]|$)'''),  # noqa: E501
    ("jwt", 3, r'''\b(ey[a-zA-Z0-9]{17,}\.ey[a-zA-Z0-9\/\\_-]{17,}\.(?:[a-zA-Z0-9\/\\_-]{10,}={0,2})?)(?:[\x60'"\s;]|\\[nr]|$)'''),  # noqa: E501
    ("jwt-base64", 2, r'''\bZXlK(?:(?P<alg>aGJHY2lPaU)|(?P<apu>aGNIVWlPaU)|(?P<apv>aGNIWWlPaU)|(?P<aud>aGRXUWlPaU)|(?P<b64>aU5qUWlP)|(?P<crit>amNtbDBJanBi)|(?P<cty>amRIa2lPaU)|(?P<epk>bGNHc2lPbn)|(?P<enc>bGJtTWlPaU)|(?P<jku>cWEzVWlPaU)|(?P<jwk>cWQyc2lPb)|(?P<iss>cGMzTWlPaU)|(?P<iv>cGRpSTZJ)|(?P<kid>cmFXUWlP)|(?P<key_ops>clpYbGZiM0J6SWpwY)|(?P<kty>cmRIa2lPaUp)|(?P<nonce>dWIyNWpaU0k2)|(?P<p2c>d01tTWlP)|(?P<p2s>d01uTWlPaU)|(?P<ppt>d2NIUWlPaU)|(?P<sub>emRXSWlPaU)|(?P<svt>emRuUWlP)|(?P<tag>MFlXY2lPaU)|(?P<typ>MGVYQWlPaUp)|(?P<url>MWNtd2l)|(?P<use>MWMyVWlPaUp)|(?P<ver>MlpYSWlPaU)|(?P<version>MlpYSnphVzl1SWpv)|(?P<x>NElqb2)|(?P<x5c>NE5XTWlP)|(?P<x5t>NE5YUWlPaU)|(?P<x5ts256>NE5YUWpVekkxTmlJNkl)|(?P<x5u>NE5YVWlPaU)|(?P<zip>NmFYQWlPaU))[a-zA-Z0-9\/\\_+\-\r\n]{40,}={0,2}'''),  # noqa: E501
    ("private-key", None, r'''(?i)-----BEGIN[ A-Z0-9_-]{0,100}PRIVATE KEY(?: BLOCK)?-----[\s\S-]{64,}?KEY(?: BLOCK)?-----'''),  # noqa: E501
    ("aws-access-token", 3, r'''\b((?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{16})\b'''),
    ("github-pat", 3, r'''ghp_[0-9a-zA-Z]{36}'''),
    ("github-oauth", 3, r'''gho_[0-9a-zA-Z]{36}'''),
    ("github-app-token", 3, r'''(?:ghu|ghs)_[0-9a-zA-Z]{36}'''),
    ("github-fine-grained-pat", 3, r'''github_pat_\w{82}'''),
    ("gitlab-pat", 3, r'''glpat-[\w-]{20}'''),
    ("slack-bot-token", 3, r'''xoxb-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*'''),
    ("slack-user-token", 2, r'''xox[pe](?:-[0-9]{10,13}){3}-[a-zA-Z0-9-]{28,34}'''),
    ("slack-app-token", 2, r'''(?i)xapp-\d-[A-Z0-9]+-\d+-[a-z0-9]+'''),
    ("openai-api-key", 3, r'''\b(sk-(?:proj|svcacct|admin)-(?:[A-Za-z0-9_-]{74}|[A-Za-z0-9_-]{58})T3BlbkFJ(?:[A-Za-z0-9_-]{74}|[A-Za-z0-9_-]{58})\b|sk-[a-zA-Z0-9]{20}T3BlbkFJ[a-zA-Z0-9]{20})(?:[\x60'"\s;]|\\[nr]|$)'''),  # noqa: E501
    ("anthropic-api-key", None, r'''\b(sk-ant-api03-[a-zA-Z0-9_\-]{93}AA)(?:[\x60'"\s;]|\\[nr]|$)'''),
    ("gcp-api-key", 4, r'''\b(AIza[\w-]{35})(?:[\x60'"\s;]|\\[nr]|$)'''),
    ("stripe-access-token", 2, r'''\b((?:sk|rk)_(?:test|live|prod)_[a-zA-Z0-9]{10,99})(?:[\x60'"\s;]|\\[nr]|$)'''),
    ("huggingface-access-token", 2, r'''\b(hf_(?i:[a-z]{34}))(?:[\x60'"\s;]|\\[nr]|$)'''),
    ("pypi-upload-token", 3, r'''pypi-AgEIcHlwaS5vcmc[\w-]{50,1000}'''),
)
# generic-api-key allowlists, verbatim: secret-target regex and match-target regex (\z -> \Z for Python).
GENERIC_SECRET_ALLOW = re.compile(r'''^[a-zA-Z_.-]+$''')
GENERIC_MATCH_ALLOW = re.compile(r'''(?i)(?:access(?:ibility|or)|access[_.-]?id|random[_.-]?access|api[_.-]?(?:id|name|version)|rapid|capital|[a-z0-9-]*?api[a-z0-9-]*?:jar:|author|X-MS-Exchange-Organization-Auth|Authentication-Results|(?:credentials?[_.-]?id|withCredentials)|(?:bucket|foreign|hot|idx|natural|primary|pub(?:lic)?|schema|sequence)[_.-]?key|(?:turkey)|key[_.-]?(?:alias|board|code|frame|id|length|mesh|name|pair|press(?:ed)?|ring|selector|signature|size|stone|storetype|word|up|down|left|right)|key[_.-]?vault[_.-]?(?:id|name)|keyVaultToStoreSecrets|key(?:store|tab)[_.-]?(?:file|path)|issuerkeyhash|(?-i:[DdMm]onkey|[DM]ONKEY)|keying|(?:secret)[_.-]?(?:length|name|size)|UserSecretsId|(?:csrf)[_.-]?token|(?:io\.jsonwebtoken[ \t]?:[ \t]?[\w-]+)|(?:api|credentials|token)[_.-]?(?:endpoint|ur[il])|public[_.-]?token|(?:key|token)[_.-]?file|(?-i:(?:[A-Z_]+=\n[A-Z_]+=|[a-z_]+=\n[a-z_]+=)(?:\n|\Z))|(?-i:(?:[A-Z.]+=\n[A-Z.]+=|[a-z.]+=\n[a-z.]+=)(?:\n|\Z)))''')  # noqa: E501
COMPILED = tuple((rule_id, entropy, re.compile(rx, re.MULTILINE)) for rule_id, entropy, rx in GITLEAKS_RULES)


def shannon_entropy(text: str) -> float:
    counts = Counter(text)
    return -sum(n / len(text) * math.log2(n / len(text)) for n in counts.values()) if text else 0.0


def scanner_findings(text: str) -> list[tuple[str, str]]:
    """(rule id, matched text) for every rule hit, applying gitleaks' entropy and generic allowlists."""
    findings = []
    for rule_id, entropy, pattern in COMPILED:
        for match in pattern.finditer(text):
            secret = next((g for g in match.groups() if g), match.group(0))
            if entropy is not None and shannon_entropy(secret) < entropy:
                continue
            if rule_id == "generic-api-key" and (GENERIC_SECRET_ALLOW.search(secret)
                                                 or GENERIC_MATCH_ALLOW.search(match.group(0))):
                continue
            findings.append((rule_id, match.group(0)))
    return findings


def runtime_credential_shapes() -> dict[str, str]:
    """Positive controls, built at runtime so no matching string is ever committed."""
    def b64(value: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()
    noise = hashlib.sha256(b"agent-movement/positive-control").hexdigest()
    return {
        "jwt": f"{b64({'alg': 'none', 'typ': 'JWT', 'kid': noise[:8]})}.{b64({'sub': noise[8:40]})}.{noise[:16]}",
        "aws-access-token": "AK" + "IA" + base64.b32encode(bytes.fromhex(noise[:20])).decode()[:16],
        "github-pat": "gh" + "p_" + noise[:36],
        "generic-api-key": "api" + "_key = " + noise[:32],
    }


class SecretScannerRuleSubsetTests(unittest.TestCase):
    def test_rule_subset_detects_runtime_positive_controls(self):
        for rule_id, value in runtime_credential_shapes().items():
            with self.subTest(rule=rule_id):
                self.assertIn(rule_id, {r for r, _ in scanner_findings(f'"{value}"\n')})

    def test_committed_files_match_no_secret_scanner_rule(self):
        self.assertGreater(len(OWNED), 20)
        for path in OWNED:
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertEqual(scanner_findings(path.read_text(encoding="utf-8")), [])

    def test_canaries_match_no_rule_in_any_seed_or_context(self):
        for seed in (receipt_fixtures.CANARY_SEED, "runtime-seed-1", "runtime-seed-2"):
            for name, value in receipt_fixtures.privacy_canaries(seed).items():
                with self.subTest(seed=seed, canary=name):
                    for context in (value, json.dumps({"authorization": value}), json.dumps({"api_key": value}),
                                    f"token = {value}\n", f"password: '{value}'"):
                        self.assertEqual(scanner_findings(context), [], context)

    def test_previous_jwt_canary_would_have_been_flagged(self):
        # The pre-#21 fixture planted a structurally valid alg:none JWT; rebuilt here at runtime.
        def b64(value: str) -> str:
            return base64.urlsafe_b64encode(value.encode()).rstrip(b"=").decode()
        old = ".".join([b64('{"alg":"none","typ":"JWT"}'), b64('{"synthetic":"canary"}'), b64("synthetic")])
        self.assertIn("jwt", {r for r, _ in scanner_findings(f'"{old}"')})
        self.assertTrue(receipts.TOKEN_LIKE.search(old))  # the verifier catches both shapes


def gitleaks_binary() -> str | None:
    return os.environ.get("GITLEAKS") or shutil.which("gitleaks")


@unittest.skipUnless(gitleaks_binary(), "gitleaks binary not found (set $GITLEAKS); the CI extras job installs it")
class GitleaksBinaryTests(unittest.TestCase):
    def test_gitleaks_default_rules_find_nothing_in_receipt_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp) / "tree"
            for path in OWNED:
                target = tree / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
            report = Path(tmp) / "gitleaks-report.json"
            result = subprocess.run([gitleaks_binary(), "dir", str(tree), "--no-banner",
                                     "--report-format", "json", "--report-path", str(report)],
                                    capture_output=True, text=True, timeout=120)
            findings = json.loads(report.read_text()) if report.exists() else None
            self.assertEqual(findings, [], result.stderr[-2000:])
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
