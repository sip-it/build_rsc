#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import pathlib
import re
import shutil
import sys
import urllib.error
import urllib.request
from collections import OrderedDict
from datetime import datetime, timezone


DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}\.?$"
)
COMMENT_PREFIXES = ("#", ";", "//")
UNSUPPORTED_GEOSITE_PREFIXES = (
    "regexp:",
    "keyword:",
    "include:",
    "cidr:",
    "geoip:",
    "process:",
    "port:",
    "@",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build MikroTik RSC and DNS adlist from runetfreedom/community sources"
    )
    parser.add_argument("--config", default="config/lists.json", help="Path to config file")
    parser.add_argument("--output", default="dist", help="Output directory")
    return parser.parse_args()


def load_json(path: pathlib.Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def fetch_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "github-actions-mikrotik-rsc/1.0",
            "Accept": "text/plain, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def fetch_optional_text(url: str) -> str | None:
    try:
        return fetch_text(url)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def ensure_clean_dir(path: pathlib.Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def normalize_geoip_line(line: str) -> str | None:
    value = line.strip()
    if not value:
        return None
    if any(value.startswith(prefix) for prefix in COMMENT_PREFIXES):
        return None

    value = value.split("#", 1)[0].strip()
    value = value.split(";", 1)[0].strip()
    if not value:
        return None

    try:
        if "/" in value:
            network = ipaddress.ip_network(value, strict=False)
            return str(network)
        addr = ipaddress.ip_address(value)
        return str(addr)
    except ValueError:
        return None


def normalize_geosite_line(line: str) -> tuple[str | None, str | None]:
    raw = line.strip()
    if not raw:
        return None, None
    if any(raw.startswith(prefix) for prefix in COMMENT_PREFIXES):
        return None, None

    raw = raw.split("#", 1)[0].strip()
    raw = raw.split(";", 1)[0].strip()
    if not raw:
        return None, None

    lower = raw.lower()
    if lower.startswith(UNSUPPORTED_GEOSITE_PREFIXES):
        return None, "unsupported_prefix"

    value = raw
    if lower.startswith("full:"):
        value = raw[5:].strip()
    elif lower.startswith("domain:"):
        value = raw[7:].strip()

    if " @" in value:
        value = value.split(" @", 1)[0].strip()
    if " " in value:
        value = value.split()[0].strip()

    value = value.lstrip(".")
    if value.startswith("*."):
        value = value[2:]

    if not value:
        return None, "empty"

    if ":" in value or "/" in value:
        return None, "unsupported_value"

    if not DOMAIN_RE.match(value):
        return None, "invalid_domain"

    return value.lower().rstrip("."), None


def normalize_self_list_line(line: str) -> tuple[str | None, str | None]:
    raw = line.strip()
    if not raw:
        return None, None
    if any(raw.startswith(prefix) for prefix in COMMENT_PREFIXES):
        return None, None

    raw = raw.split("#", 1)[0].strip()
    raw = raw.split(";", 1)[0].strip()
    if not raw:
        return None, None

    geoip = normalize_geoip_line(raw)
    if geoip is not None:
        return geoip, "geoip"

    geosite, _ = normalize_geosite_line(raw)
    if geosite is not None:
        return geosite, "geosite"

    return None, None


def expand_domain_entries(
    entries: list[str],
    add_www: bool,
    skip_www_prefixes: set[str] | None = None,
) -> list[str]:
    result: OrderedDict[str, None] = OrderedDict()
    skip_www_prefixes = skip_www_prefixes or set()

    for entry in entries:
        normalized = entry.lower().rstrip(".")
        if not normalized:
            continue

        result.setdefault(normalized, None)

        if not add_www:
            continue

        if normalized.startswith("www."):
            continue

        first_label = normalized.split(".", 1)[0]
        if first_label in skip_www_prefixes:
            continue

        result.setdefault(f"www.{normalized}", None)

    return list(result.keys())


def filter_unique_entries(entries: list[str], seen: set[str]) -> tuple[list[str], int]:
    result: list[str] = []
    duplicates = 0
    for entry in entries:
        if entry in seen:
            duplicates += 1
            continue
        seen.add(entry)
        result.append(entry)
    return result, duplicates


def build_remove_line(list_name: str, comment: str) -> str:
    return f'/ip firewall address-list remove [find where list="{list_name}" comment="{comment}"]'


def build_add_lines(list_name: str, entries: list[str], comment: str, is_domain: bool) -> list[str]:
    lines = ["/ip firewall address-list"]
    for entry in entries:
        if is_domain:
            lines.append(f'add list="{list_name}" address="{entry}" comment="{comment}"')
        else:
            lines.append(f'add list="{list_name}" address={entry} comment="{comment}"')
    return lines


def render_routeros_update_script(combined_relative_path: str) -> str:
    return "\n".join(
        [
            "# Example update script for RouterOS",
            "/system script",
            "add name=rf-update-community policy=read,write,test source={",
            '    :local baseUrl "https://raw.githubusercontent.com/sip-it/build_rsc/release"',
            f'    :local file "{combined_relative_path}"',
            '    :local url ($baseUrl . "/" . $file)',
            '    :local dst "tmp-community-antifilter.rsc"',
            '    :log info ("rf-update-community: downloading " . $url)',
            '    :do {',
            '        /tool fetch url=$url dst-path=$dst keep-result=yes',
            '        :if ([:len [/file find where name=$dst]] = 0) do={',
            '            :error ("download failed: " . $file)',
            '        }',
            '        /import file-name=$dst verbose=yes',
            '        /file remove [find where name=$dst]',
            '        :log info ("rf-update-community: imported " . $file)',
            '    } on-error={',
            '        :log error ("rf-update-community: failed " . $file)',
            '        :if ([:len [/file find where name=$dst]] > 0) do={',
            '            /file remove [find where name=$dst]',
            '        }',
            '    }',
            '}',
            '',
        ]
    )


def render_release_readme(
    repo_owner: str,
    repo_name: str,
    release_branch: str,
    combined_relative_path: str,
    dns_relative_path: str,
    routeros_relative_path: str,
) -> str:
    raw_base = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{release_branch}"

    combined_url = f"{raw_base}/{combined_relative_path}"
    dns_url = f"{raw_base}/{dns_relative_path}"
    routeros_url = f"{raw_base}/{routeros_relative_path}"

    return "\n".join(
        [
            "# Generated release files",
            "",
            "Полезные ссылки:",
            "",
            f"- community-antifilter.rsc: `{combined_url}`",
            f"- dns adlist category-ads-all.txt: `{dns_url}`",
            f"- RouterOS update script example: `{routeros_url}`",
            "",
            "Содержимое `community-antifilter.rsc`:",
            "- geoip:ru-blocked-community",
            "- geosite:antifilter-download-community",
            "- self-list.txt из ветки `self-list`, если файл существует",
            "",
            "Особенности сборки:",
            "- geosite:category-ads-all не включается в общий `.rsc`, только в отдельный DNS adlist",
            "- доменные записи в общем `.rsc` дополняются вариантом с `www.`",
            "- `www.` не добавляется для доменов, начинающихся с `api.` или `cdn.`",
            "- при дедупликации приоритет у community-источников, потом self-list",
            "",
        ]
    )


def main() -> int:
    args = parse_args()
    config_path = pathlib.Path(args.config).resolve()
    output_root = pathlib.Path(args.output).resolve()

    config = load_json(config_path)

    repo_owner = config["repository"]["owner"]
    repo_name = config["repository"]["name"]
    release_branch = config["repository"]["release_branch"]

    geoip_base = config["sources"]["geoip_base"].rstrip("/")
    geosite_base = config["sources"]["geosite_base"].rstrip("/")

    combined_relative_path = config["output"]["combined_rsc"]
    routeros_relative_path = config["output"]["routeros_script"]
    dns_relative_path = config["output"]["dns_adlist"]
    readme_relative_path = config["output"]["readme"]

    bundle_list_name = config["bundle"]["list_name"]
    geoip_categories = config["bundle"].get("geoip_categories", [])
    geosite_categories = config["bundle"].get("geosite_categories", [])

    dns_adlist_category = config["dns_adlist"]["category"]

    self_list_cfg = config.get("self_list", {})
    self_list_enabled = self_list_cfg.get("enabled", False)
    self_list_branch = self_list_cfg.get("branch", "self-list")
    self_list_path = self_list_cfg.get("path", "self-list.txt")
    self_list_optional = self_list_cfg.get("optional", True)

    domain_variants_cfg = config.get("domain_variants", {})
    add_www_in_combined_rsc = domain_variants_cfg.get("add_www_in_combined_rsc", False)
    skip_www_prefixes = {
        str(prefix).strip().lower()
        for prefix in domain_variants_cfg.get("skip_www_for_prefixes", [])
        if str(prefix).strip()
    }
    dedup_cfg = config.get("deduplication", {})
    dedup_enabled = dedup_cfg.get("enabled", True)

    ensure_clean_dir(output_root)

    raw_dir = output_root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    combined_path = output_root / combined_relative_path
    combined_path.parent.mkdir(parents=True, exist_ok=True)

    dns_adlist_path = output_root / dns_relative_path
    dns_adlist_path.parent.mkdir(parents=True, exist_ok=True)

    routeros_path = output_root / routeros_relative_path
    routeros_path.parent.mkdir(parents=True, exist_ok=True)

    release_readme_path = output_root / readme_relative_path
    release_readme_path.parent.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": config["repository"],
        "sources": config["sources"],
        "output": config["output"],
        "bundle": config["bundle"],
        "dns_adlist": config["dns_adlist"],
        "self_list": self_list_cfg,
        "domain_variants": config.get("domain_variants", {}),
        "deduplication": dedup_cfg,
        "stats": {
            "geoip": {},
            "geosite": {},
            "self_list": {},
            "dns_adlist": {},
        },
    }

    combined_lines: list[str] = [
        "# Combined MikroTik RSC generated from runetfreedom/community sources",
        f"# Generated at {manifest['generated_at']}",
        "",
    ]

    seen_geoip: set[str] = set()
    seen_domains: set[str] = set()

    community_geoip_blocks: list[list[str]] = []
    community_geosite_blocks: list[list[str]] = []
    self_geoip_block: list[str] = []
    self_geosite_block: list[str] = []

    for name in geoip_categories:
        url = f"{geoip_base}/{name}.txt"
        print(f"build geoip:{name}")
        content = fetch_text(url)
        (raw_dir / f"geoip-{name}.txt").write_text(content, encoding="utf-8", newline="\n")

        entries_map: OrderedDict[str, None] = OrderedDict()
        invalid = 0
        for line in content.splitlines():
            normalized = normalize_geoip_line(line)
            if normalized is None:
                invalid += 1
                continue
            entries_map.setdefault(normalized, None)

        entries = list(entries_map.keys())
        duplicates_skipped = 0
        if dedup_enabled:
            entries, duplicates_skipped = filter_unique_entries(entries, seen_geoip)

        comment = f"src=github:geoip:{name}"
        if entries:
            community_geoip_blocks.append(
                [
                    f"# geoip:{name}",
                    build_remove_line(bundle_list_name, comment),
                    *build_add_lines(bundle_list_name, entries, comment, is_domain=False),
                    "",
                ]
            )

        manifest["stats"]["geoip"][name] = {
            "entries": len(entries),
            "invalid_or_skipped": invalid,
            "duplicates_skipped": duplicates_skipped,
            "comment": comment,
            "source_url": url,
        }

    for name in geosite_categories:
        url = f"{geosite_base}/{name}.txt"
        print(f"build geosite:{name}")
        content = fetch_text(url)
        (raw_dir / f"geosite-{name}.txt").write_text(content, encoding="utf-8", newline="\n")

        entries_map: OrderedDict[str, None] = OrderedDict()
        skipped: dict[str, int] = {}
        for line in content.splitlines():
            normalized, reason = normalize_geosite_line(line)
            if normalized is None:
                if reason:
                    skipped[reason] = skipped.get(reason, 0) + 1
                continue
            entries_map.setdefault(normalized, None)

        entries = expand_domain_entries(
            list(entries_map.keys()),
            add_www_in_combined_rsc,
            skip_www_prefixes,
        )
        duplicates_skipped = 0
        if dedup_enabled:
            entries, duplicates_skipped = filter_unique_entries(entries, seen_domains)

        comment = f"src=github:geosite:{name}"
        if entries:
            community_geosite_blocks.append(
                [
                    f"# geosite:{name}",
                    build_remove_line(bundle_list_name, comment),
                    *build_add_lines(bundle_list_name, entries, comment, is_domain=True),
                    "",
                ]
            )

        manifest["stats"]["geosite"][name] = {
            "entries": len(entries),
            "skipped": skipped,
            "duplicates_skipped": duplicates_skipped,
            "comment": comment,
            "source_url": url,
        }

    if self_list_enabled:
        self_list_url = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{self_list_branch}/{self_list_path}"
        print(f"build self-list:{self_list_url}")

        content = fetch_optional_text(self_list_url) if self_list_optional else fetch_text(self_list_url)

        if content is None:
            manifest["stats"]["self_list"] = {
                "enabled": True,
                "found": False,
                "optional": self_list_optional,
                "source_url": self_list_url,
            }
        else:
            (raw_dir / "self-list.txt").write_text(content, encoding="utf-8", newline="\n")

            geoip_entries_map: OrderedDict[str, None] = OrderedDict()
            geosite_entries_map: OrderedDict[str, None] = OrderedDict()
            ignored = 0

            for line in content.splitlines():
                normalized, entry_type = normalize_self_list_line(line)
                if normalized is None or entry_type is None:
                    ignored += 1
                    continue
                if entry_type == "geoip":
                    geoip_entries_map.setdefault(normalized, None)
                elif entry_type == "geosite":
                    geosite_entries_map.setdefault(normalized, None)

            self_geoip_entries = list(geoip_entries_map.keys())
            self_geosite_entries = expand_domain_entries(
                list(geosite_entries_map.keys()),
                add_www_in_combined_rsc,
                skip_www_prefixes,
            )

            self_geoip_duplicates = 0
            self_geosite_duplicates = 0

            if dedup_enabled:
                self_geoip_entries, self_geoip_duplicates = filter_unique_entries(self_geoip_entries, seen_geoip)
                self_geosite_entries, self_geosite_duplicates = filter_unique_entries(self_geosite_entries, seen_domains)

            self_geoip_comment = "src=github:self-list:geoip"
            self_geosite_comment = "src=github:self-list:geosite"

            if self_geoip_entries:
                self_geoip_block = [
                    "# self-list geoip",
                    build_remove_line(bundle_list_name, self_geoip_comment),
                    *build_add_lines(bundle_list_name, self_geoip_entries, self_geoip_comment, is_domain=False),
                    "",
                ]

            if self_geosite_entries:
                self_geosite_block = [
                    "# self-list geosite",
                    build_remove_line(bundle_list_name, self_geosite_comment),
                    *build_add_lines(bundle_list_name, self_geosite_entries, self_geosite_comment, is_domain=True),
                    "",
                ]

            manifest["stats"]["self_list"] = {
                "enabled": True,
                "found": True,
                "optional": self_list_optional,
                "source_url": self_list_url,
                "geoip_entries": len(self_geoip_entries),
                "geosite_entries": len(self_geosite_entries),
                "ignored": ignored,
                "geoip_duplicates_skipped": self_geoip_duplicates,
                "geosite_duplicates_skipped": self_geosite_duplicates,
                "geoip_comment": self_geoip_comment,
                "geosite_comment": self_geosite_comment,
            }

    for block in community_geoip_blocks:
        combined_lines.extend(block)
    for block in community_geosite_blocks:
        combined_lines.extend(block)
    if self_geoip_block:
        combined_lines.extend(self_geoip_block)
    if self_geosite_block:
        combined_lines.extend(self_geosite_block)

    combined_path.write_text("\n".join(combined_lines).rstrip() + "\n", encoding="utf-8", newline="\n")

    dns_url = f"{geosite_base}/{dns_adlist_category}.txt"
    print(f"build dns-adlist:{dns_adlist_category}")
    dns_content = fetch_text(dns_url)
    (raw_dir / f"geosite-{dns_adlist_category}.txt").write_text(dns_content, encoding="utf-8", newline="\n")

    dns_entries_map: OrderedDict[str, None] = OrderedDict()
    skipped_dns: dict[str, int] = {}
    for line in dns_content.splitlines():
        normalized, reason = normalize_geosite_line(line)
        if normalized is None:
            if reason:
                skipped_dns[reason] = skipped_dns.get(reason, 0) + 1
            continue
        dns_entries_map.setdefault(normalized, None)

    dns_entries = list(dns_entries_map.keys())
    dns_adlist_path.write_text("\n".join(dns_entries).rstrip() + "\n", encoding="utf-8", newline="\n")

    manifest["stats"]["dns_adlist"] = {
        "category": dns_adlist_category,
        "entries": len(dns_entries),
        "skipped": skipped_dns,
        "source_url": dns_url,
    }

    routeros_path.write_text(
        render_routeros_update_script(combined_relative_path),
        encoding="utf-8",
        newline="\n",
    )

    release_readme_path.write_text(
        render_release_readme(
            repo_owner=repo_owner,
            repo_name=repo_name,
            release_branch=release_branch,
            combined_relative_path=combined_relative_path,
            dns_relative_path=dns_relative_path,
            routeros_relative_path=routeros_relative_path,
        ),
        encoding="utf-8",
        newline="\n",
    )

    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
