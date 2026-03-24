#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

USER_AGENT = "github-actions-mikrotik-rsc/1.0"
COMMENT_RE = re.compile(r"\s+#.*$")
DOMAIN_RE = re.compile(r"^[A-Za-z0-9.-]+$")
UNSUPPORTED_PREFIXES = (
    "regexp:",
    "keyword:",
    "include:",
    "regexp(",
    "domain-regexp:",
)


@dataclass
class BuildResult:
    kind: str
    category: str
    list_name: str
    source_url: str
    output_path: str
    entries: int
    skipped: dict[str, int]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")


def fetch_text(url: str, timeout: int = 120) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} while fetching {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc


def sort_networks(values: Iterable[str]) -> list[str]:
    nets = [ipaddress.ip_network(v, strict=False) for v in values]
    nets.sort(key=lambda n: (n.version, int(n.network_address), n.prefixlen))
    return [str(n) for n in nets]


def strip_inline_comment(line: str) -> str:
    return COMMENT_RE.sub("", line).strip()


def parse_geoip(text: str) -> tuple[list[str], Counter]:
    entries: set[str] = set()
    skipped: Counter[str] = Counter()

    for raw in text.splitlines():
        line = strip_inline_comment(raw)
        if not line or line.startswith(("#", ";", "//")):
            continue

        token = line.split()[0]
        if "," in token:
            parts = [p.strip() for p in token.split(",") if p.strip()]
            token = parts[-1]

        try:
            network = ipaddress.ip_network(token, strict=False)
        except ValueError:
            skipped["invalid_ip"] += 1
            continue

        entries.add(str(network))

    return sort_networks(entries), skipped


def normalize_domain(value: str) -> tuple[str | None, str | None]:
    line = strip_inline_comment(value)
    if not line or line.startswith(("#", ";", "//")):
        return None, None

    lower = line.lower()
    if lower.startswith(UNSUPPORTED_PREFIXES):
        return None, "unsupported_operator"

    for prefix in ("full:", "domain:"):
        if lower.startswith(prefix):
            line = line[len(prefix):].strip()
            lower = line.lower()
            break

    if lower.startswith(("http://", "https://")):
        parsed = urlsplit(line)
        line = parsed.hostname or ""

    if line.startswith("||"):
        line = line[2:]
    elif line.startswith("|"):
        line = line[1:]

    while line.startswith(("*.", "+.", ".")):
        if line.startswith(("*.", "+.")):
            line = line[2:]
        else:
            line = line[1:]

    line = line.split("/")[0].split("^")[0].strip().strip(".").lower()

    if not line:
        return None, "empty"
    if any(ch in line for ch in ("*", "[", "]", "(", ")", "{", "}", "\\", "!", "@")):
        return None, "unsupported_pattern"
    if not DOMAIN_RE.fullmatch(line):
        return None, "invalid_domain"
    if "." not in line:
        return None, "not_fqdn"

    return line, None


def parse_geosite(text: str) -> tuple[list[str], Counter]:
    entries: set[str] = set()
    skipped: Counter[str] = Counter()

    for raw in text.splitlines():
        domain, reason = normalize_domain(raw)
        if domain:
            entries.add(domain)
        elif reason:
            skipped[reason] += 1

    return sorted(entries), skipped


def render_rsc(kind: str, category: str, list_name: str, entries: list[str], comment_prefix: str, generated_at: str) -> str:
    tag = f"{comment_prefix};kind={kind};category={category}"
    lines = [
        f"# generated_at={generated_at}",
        f"# kind={kind}",
        f"# category={category}",
        f'/ip firewall address-list remove [find where list="{list_name}" and comment="{tag}"]',
        "/ip firewall address-list",
    ]

    if kind == "geoip":
        for entry in entries:
            lines.append(f'add list="{list_name}" address={entry} comment="{tag}"')
    else:
        for entry in entries:
            lines.append(f'add list="{list_name}" address="{entry}" comment="{tag}"')

    lines.append("")
    return "\n".join(lines)


def build_one(kind: str, category: str, cfg: dict, out_dir: Path, generated_at: str) -> BuildResult:
    list_prefix = cfg["mikrotik"]["list_prefix"]
    comment_prefix = cfg["mikrotik"]["comment_prefix"]
    list_name = f"{list_prefix}-{kind}-{slugify(category)}"

    if kind == "geoip":
        url = f"{cfg['source']['geoip_base_url'].rstrip('/')}/{category}.txt"
        content = fetch_text(url)
        entries, skipped = parse_geoip(content)
    else:
        url = f"{cfg['source']['geosite_base_url'].rstrip('/')}/{category}.txt"
        content = fetch_text(url)
        entries, skipped = parse_geosite(content)

    rel_path = Path("rsc") / kind / f"{category}.rsc"
    abs_path = out_dir / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(render_rsc(kind, category, list_name, entries, comment_prefix, generated_at), encoding="utf-8")

    return BuildResult(
        kind=kind,
        category=category,
        list_name=list_name,
        source_url=url,
        output_path=rel_path.as_posix(),
        entries=len(entries),
        skipped=dict(skipped),
    )


def write_routeros_helper(results: list[BuildResult], out_dir: Path, publish_repo: str, publish_branch: str) -> None:
    base_url = f"https://raw.githubusercontent.com/{publish_repo}/{publish_branch}"
    files = ";".join(result.output_path for result in results)
    helper = f'''# import this file into RouterOS, then create /system scheduler on rf-update-all
/system script
add name="rf-update-all" policy=read,write,test source={{
    :local baseUrl "{base_url}"
    :local files {{{';'.join(f'"{result.output_path}"' for result in results)}}}

    :foreach f in=$files do={{
        :local url ($baseUrl . "/" . $f)
        :local dst ("tmp-" . [:pick $f ([:find $f "/" -1] + 1) [:len $f]])

        :log info ("rf-update-all: fetching " . $url)
        :do {{
            /tool fetch url=$url dst-path=$dst keep-result=yes
            /import file-name=$dst verbose=yes
            /file remove [find where name=$dst]
        }} on-error={{
            :log error ("rf-update-all: failed " . $url)
            :if ([:len [/file find where name=$dst]] > 0) do={{
                /file remove [find where name=$dst]
            }}
        }}
    }}
}}
'''
    helper_dir = out_dir / "routeros"
    helper_dir.mkdir(parents=True, exist_ok=True)
    (helper_dir / "rf-update-all.example.rsc").write_text(helper, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build MikroTik .rsc address-list files from runetfreedom sources")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--publish-repo", default=os.getenv("GITHUB_REPOSITORY", "OWNER/REPO"))
    parser.add_argument("--publish-branch", default="release")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = utc_now()

    results: list[BuildResult] = []
    errors: list[str] = []

    for kind in ("geoip", "geosite"):
        for category in config.get(kind, []):
            print(f"::group::build {kind}:{category}")
            try:
                result = build_one(kind, category, config, out_dir, generated_at)
                results.append(result)
                print(f"source={result.source_url}")
                print(f"entries={result.entries}")
                if result.skipped:
                    print(f"skipped={json.dumps(result.skipped, ensure_ascii=False, sort_keys=True)}")
            except Exception as exc:  # noqa: BLE001
                msg = f"{kind}:{category}: {exc}"
                errors.append(msg)
                print(f"::error::{msg}")
            finally:
                print("::endgroup::")

    manifest = {
        "generated_at": generated_at,
        "publish_repo": args.publish_repo,
        "publish_branch": args.publish_branch,
        "results": [result.__dict__ for result in results],
        "errors": errors,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.publish_repo and "/" in args.publish_repo:
        write_routeros_helper(results, out_dir, args.publish_repo, args.publish_branch)

    urls_txt = []
    if args.publish_repo and "/" in args.publish_repo:
        raw_base = f"https://raw.githubusercontent.com/{args.publish_repo}/{args.publish_branch}"
        for item in results:
            urls_txt.append(f"{item.list_name} {raw_base}/{item.output_path}")
        (out_dir / "routeros" / "urls.txt").write_text("\n".join(urls_txt) + "\n", encoding="utf-8")

    if errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
