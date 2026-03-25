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
from typing import Any

DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?!-)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}\.?$")
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
    parser = argparse.ArgumentParser(description="Build one combined MikroTik RSC and separate DNS adlist")
    parser.add_argument("--config", default="config/lists.json", help="Path to lists.json")
    parser.add_argument("--output", default="dist", help="Output directory")
    return parser.parse_args()


def load_json(path: pathlib.Path) -> dict[str, Any]:
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
    with urllib.request.urlopen(req, timeout=120) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def fetch_optional_text(url: str, optional: bool) -> str | None:
    try:
        return fetch_text(url)
    except urllib.error.HTTPError as exc:
        if optional and exc.code == 404:
            return None
        raise
    except urllib.error.URLError:
        if optional:
            return None
        raise


def ensure_clean_dir(path: pathlib.Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def strip_comments(value: str) -> str:
    value = value.split("#", 1)[0].strip()
    value = value.split(";", 1)[0].strip()
    return value


def normalize_geoip_line(line: str) -> str | None:
    value = line.strip()
    if not value:
        return None
    if any(value.startswith(prefix) for prefix in COMMENT_PREFIXES):
        return None
    value = strip_comments(value)
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

    raw = strip_comments(raw)
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


def sanitize_comment_source(kind: str, category: str) -> str:
    return f"src=github:{kind}:{category}"


def write_raw_copy(raw_dir: pathlib.Path, filename: str, content: str) -> None:
    (raw_dir / filename).write_text(content, encoding="utf-8", newline="\n")


def build_remove_line(list_name: str, comment: str) -> str:
    return f'/ip firewall address-list remove [find where list="{list_name}" comment="{comment}"]'


def build_add_lines(list_name: str, entries: list[str], comment: str, is_domain: bool) -> list[str]:
    lines = ["/ip firewall address-list"]
    if is_domain:
        lines.extend(f'add list="{list_name}" address="{entry}" comment="{comment}"' for entry in entries)
    else:
        lines.extend(f'add list="{list_name}" address={entry} comment="{comment}"' for entry in entries)
    return lines


def render_routeros_update_script(combined_relative_path: str, raw_base_url: str) -> str:
    return "\n".join(
        [
            "# Example update script for RouterOS",
            "/system script",
            "add name=rf-update-community policy=read,write,test source={",
            f'    :local baseUrl "{raw_base_url}"',
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


def render_readme(
    *,
    generated_at: str,
    release_branch: str,
    combined_raw_url: str,
    dns_adlist_raw_url: str,
    routeros_raw_url: str,
    used_categories: list[str],
    optional_geoip_categories: list[str],
    self_list_source_url: str | None,
    self_list_optional: bool,
    bundle_list_name: str,
) -> str:
    used_lines = "\n".join(f"- `{item}`" for item in used_categories)
    optional_lines = "\n".join(f"- `geoip:{item}`" for item in optional_geoip_categories)
    self_list_block = ""
    if self_list_source_url:
        self_list_block = (
            "\n## self-list\n\n"
            f"- источник: `{self_list_source_url}`\n"
            f"- optional: `{str(self_list_optional).lower()}`\n"
            f"- строки с доменами и IP/CIDR добавляются в общий list `{bundle_list_name}`\n"
        )

    optional_block = ""
    if optional_geoip_categories:
        optional_block = (
            "\n## Дополнительные geoip-категории (поддерживаются конфигом)\n\n"
            "Сейчас они не включены в итоговый `.rsc`, но их можно включить в `config/lists.json`.\n\n"
            f"{optional_lines}\n"
        )

    return f"""# release artifacts

Сгенерировано: `{generated_at}`
Ветка публикации: `{release_branch}`

## Готовые ссылки

- Combined MikroTik RSC: `{combined_raw_url}`
- DNS adlist (`category-ads-all`): `{dns_adlist_raw_url}`
- RouterOS update script: `{routeros_raw_url}`

## Что входит в combined RSC

- общий list name: `{bundle_list_name}`
{used_lines}
{self_list_block}{optional_block}
## MikroTik CHR

Импорт напрямую:

```rsc
/tool fetch url="{combined_raw_url}" dst-path=community-antifilter.rsc keep-result=yes
/import file-name=community-antifilter.rsc verbose=yes
/file remove [find where name=community-antifilter.rsc]
```

Или импортируй готовый update-script:

```rsc
/tool fetch url="{routeros_raw_url}" dst-path=rf-update-community.rsc keep-result=yes
/import file-name=rf-update-community.rsc verbose=yes
```
"""


def main() -> int:
    args = parse_args()
    config_path = pathlib.Path(args.config).resolve()
    output_root = pathlib.Path(args.output).resolve()

    config = load_json(config_path)
    repo = config["repository"]
    sources = config["sources"]
    output_cfg = config.get("output", {})
    bundle_cfg = config.get("bundle", {})
    self_list_cfg = config.get("self_list", {})
    extra_geoip_cfg = config.get("optional_geoip_categories", {})

    owner = repo["owner"]
    name = repo["name"]
    release_branch = repo.get("release_branch", "release")
    raw_base_url = f"https://raw.githubusercontent.com/{owner}/{name}/{release_branch}"

    geosite_base = sources["geosite_base"].rstrip("/")
    geoip_base = sources["geoip_base"].rstrip("/")

    combined_relative_path = output_cfg.get("combined_rsc", "rsc/community-antifilter.rsc")
    routeros_relative_path = output_cfg.get("routeros_script", "routeros/rf-update-community.rsc")
    dns_adlist_relative_path = output_cfg.get("dns_adlist", "dns/category-ads-all.txt")
    readme_relative_path = output_cfg.get("readme", "README.md")

    bundle_list_name = bundle_cfg.get("list_name", "antifilter-community")
    bundle_geoip_categories = list(bundle_cfg.get("geoip_categories", ["ru-blocked-community"]))
    bundle_geosite_categories = list(bundle_cfg.get("geosite_categories", ["antifilter-download-community", "category-ads-all"]))

    dns_adlist_name = config.get("dns_adlist", "category-ads-all")

    self_list_enabled = bool(self_list_cfg.get("enabled", False))
    self_list_branch = self_list_cfg.get("branch", "self-list")
    self_list_path = self_list_cfg.get("path", "self-list.txt")
    self_list_optional = bool(self_list_cfg.get("optional", True))
    self_list_comment = self_list_cfg.get("comment_label", "self-list")
    self_list_url = None
    if self_list_enabled:
        self_list_url = f"https://raw.githubusercontent.com/{owner}/{name}/{self_list_branch}/{self_list_path}"

    optional_geoip_enabled = bool(extra_geoip_cfg.get("enabled", False))
    optional_geoip_optional = bool(extra_geoip_cfg.get("optional", True))
    optional_geoip_categories = list(extra_geoip_cfg.get("categories", []))

    ensure_clean_dir(output_root)
    raw_dir = output_root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    combined_path = output_root / combined_relative_path
    combined_path.parent.mkdir(parents=True, exist_ok=True)
    routeros_path = output_root / routeros_relative_path
    routeros_path.parent.mkdir(parents=True, exist_ok=True)
    dns_adlist_path = output_root / dns_adlist_relative_path
    dns_adlist_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path = output_root / readme_relative_path
    readme_path.parent.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).isoformat()
    used_categories: list[str] = []
    combined_lines: list[str] = []
    dns_entries: OrderedDict[str, None] = OrderedDict()

    manifest: dict[str, Any] = {
        "generated_at": generated_at,
        "repository": repo,
        "sources": sources,
        "bundle": {
            "list_name": bundle_list_name,
            "geoip_categories": bundle_geoip_categories,
            "geosite_categories": bundle_geosite_categories,
        },
        "optional_geoip_categories": {
            "enabled": optional_geoip_enabled,
            "optional": optional_geoip_optional,
            "categories": optional_geoip_categories,
        },
        "self_list": {
            "enabled": self_list_enabled,
            "url": self_list_url,
            "optional": self_list_optional,
            "comment_label": self_list_comment,
        },
        "files": [
            {
                "kind": "combined",
                "relative_path": combined_relative_path,
                "raw_url": f"{raw_base_url}/{combined_relative_path}",
            },
            {
                "kind": "dns_adlist",
                "relative_path": dns_adlist_relative_path,
                "raw_url": f"{raw_base_url}/{dns_adlist_relative_path}",
            },
            {
                "kind": "routeros_script",
                "relative_path": routeros_relative_path,
                "raw_url": f"{raw_base_url}/{routeros_relative_path}",
            },
            {
                "kind": "readme",
                "relative_path": readme_relative_path,
                "raw_url": f"{raw_base_url}/{readme_relative_path}",
            },
        ],
        "stats": {"geoip": {}, "geosite": {}, "dns_adlist": {}, "self_list": {}},
    }

    def append_header() -> None:
        combined_lines.extend(
            [
                "# Combined MikroTik RSC generated from configured sources",
                f"# Generated at {generated_at}",
                f"# List name: {bundle_list_name}",
                "# Included categories:",
            ]
        )
        combined_lines.extend(f"# - {item}" for item in used_categories)
        combined_lines.append("")

    geoip_sources: list[tuple[str, bool]] = [(category, False) for category in bundle_geoip_categories]
    if optional_geoip_enabled:
        geoip_sources.extend((category, optional_geoip_optional) for category in optional_geoip_categories)

    geoip_blocks: list[list[str]] = []
    geosite_blocks: list[list[str]] = []

    for category, is_optional in geoip_sources:
        print(f"build geoip:{category}")
        url = f"{geoip_base}/{category}.txt"
        try:
            content = fetch_optional_text(url, is_optional)
        except urllib.error.URLError as exc:
            raise SystemExit(f"failed to download {url}: {exc}") from exc
        if content is None:
            manifest["stats"]["geoip"][category] = {"status": "skipped_optional_missing", "source_url": url}
            continue

        write_raw_copy(raw_dir, f"geoip-{category}.txt", content)
        entries: OrderedDict[str, None] = OrderedDict()
        invalid = 0
        for line in content.splitlines():
            normalized = normalize_geoip_line(line)
            if normalized is None:
                invalid += 1
                continue
            entries.setdefault(normalized, None)

        comment = sanitize_comment_source("geoip", category)
        block = [f"# geoip:{category}", build_remove_line(bundle_list_name, comment)]
        block.extend(build_add_lines(bundle_list_name, list(entries.keys()), comment, is_domain=False))
        block.append("")
        geoip_blocks.append(block)
        used_categories.append(f"geoip:{category}")
        manifest["stats"]["geoip"][category] = {
            "list_name": bundle_list_name,
            "entries": len(entries),
            "invalid_or_skipped": invalid,
            "source_url": url,
            "comment": comment,
        }

    for category in bundle_geosite_categories:
        print(f"build geosite:{category}")
        url = f"{geosite_base}/{category}.txt"
        try:
            content = fetch_text(url)
        except urllib.error.URLError as exc:
            raise SystemExit(f"failed to download {url}: {exc}") from exc

        write_raw_copy(raw_dir, f"geosite-{category}.txt", content)
        entries: OrderedDict[str, None] = OrderedDict()
        skipped: dict[str, int] = {}
        for line in content.splitlines():
            normalized, reason = normalize_geosite_line(line)
            if normalized is None:
                if reason:
                    skipped[reason] = skipped.get(reason, 0) + 1
                continue
            entries.setdefault(normalized, None)
            if category == dns_adlist_name:
                dns_entries.setdefault(normalized, None)

        comment = sanitize_comment_source("geosite", category)
        block = [f"# geosite:{category}", build_remove_line(bundle_list_name, comment)]
        block.extend(build_add_lines(bundle_list_name, list(entries.keys()), comment, is_domain=True))
        block.append("")
        geosite_blocks.append(block)
        used_categories.append(f"geosite:{category}")
        manifest["stats"]["geosite"][category] = {
            "list_name": bundle_list_name,
            "entries": len(entries),
            "skipped": skipped,
            "source_url": url,
            "comment": comment,
        }

    if self_list_enabled and self_list_url:
        print(f"build self_list:{self_list_url}")
        content = fetch_optional_text(self_list_url, self_list_optional)
        if content is None:
            manifest["stats"]["self_list"] = {"status": "skipped_optional_missing", "source_url": self_list_url}
        else:
            write_raw_copy(raw_dir, "self-list.txt", content)
            geoip_entries: OrderedDict[str, None] = OrderedDict()
            geosite_entries: OrderedDict[str, None] = OrderedDict()
            invalid = 0
            skipped: dict[str, int] = {}
            for line in content.splitlines():
                geoip_value = normalize_geoip_line(line)
                if geoip_value is not None:
                    geoip_entries.setdefault(geoip_value, None)
                    continue
                geosite_value, reason = normalize_geosite_line(line)
                if geosite_value is not None:
                    geosite_entries.setdefault(geosite_value, None)
                    continue
                stripped = strip_comments(line.strip())
                if stripped:
                    invalid += 1
                    if reason:
                        skipped[reason] = skipped.get(reason, 0) + 1

            comment = f"src=github:{self_list_comment}"
            if geoip_entries:
                geoip_blocks.append(
                    [
                        "# self-list geoip",
                        build_remove_line(bundle_list_name, comment),
                        *build_add_lines(bundle_list_name, list(geoip_entries.keys()), comment, is_domain=False),
                        "",
                    ]
                )
            if geosite_entries:
                geosite_blocks.append(
                    [
                        "# self-list geosite",
                        build_remove_line(bundle_list_name, comment),
                        *build_add_lines(bundle_list_name, list(geosite_entries.keys()), comment, is_domain=True),
                        "",
                    ]
                )
            used_categories.append(self_list_comment)
            manifest["stats"]["self_list"] = {
                "status": "loaded",
                "source_url": self_list_url,
                "list_name": bundle_list_name,
                "geoip_entries": len(geoip_entries),
                "geosite_entries": len(geosite_entries),
                "invalid_or_skipped": invalid,
                "geosite_skipped": skipped,
                "comment": comment,
            }

    if dns_adlist_name not in bundle_geosite_categories:
        print(f"build dns_adlist:{dns_adlist_name}")
        url = f"{geosite_base}/{dns_adlist_name}.txt"
        try:
            content = fetch_text(url)
        except urllib.error.URLError as exc:
            raise SystemExit(f"failed to download {url}: {exc}") from exc
        write_raw_copy(raw_dir, f"geosite-{dns_adlist_name}.txt", content)
        skipped: dict[str, int] = {}
        for line in content.splitlines():
            normalized, reason = normalize_geosite_line(line)
            if normalized is None:
                if reason:
                    skipped[reason] = skipped.get(reason, 0) + 1
                continue
            dns_entries.setdefault(normalized, None)
        manifest["stats"]["dns_adlist"][dns_adlist_name] = {
            "entries": len(dns_entries),
            "skipped": skipped,
            "source_url": url,
        }
    else:
        source_url = f"{geosite_base}/{dns_adlist_name}.txt"
        manifest["stats"]["dns_adlist"][dns_adlist_name] = {
            "entries": len(dns_entries),
            "skipped": manifest["stats"]["geosite"][dns_adlist_name]["skipped"],
            "source_url": source_url,
        }

    append_header()
    for block in geoip_blocks + geosite_blocks:
        combined_lines.extend(block)

    combined_path.write_text("\n".join(combined_lines).rstrip() + "\n", encoding="utf-8", newline="\n")
    dns_adlist_path.write_text("\n".join(dns_entries.keys()).rstrip() + "\n", encoding="utf-8", newline="\n")
    routeros_path.write_text(render_routeros_update_script(combined_relative_path, raw_base_url), encoding="utf-8", newline="\n")
    readme_path.write_text(
        render_readme(
            generated_at=generated_at,
            release_branch=release_branch,
            combined_raw_url=f"{raw_base_url}/{combined_relative_path}",
            dns_adlist_raw_url=f"{raw_base_url}/{dns_adlist_relative_path}",
            routeros_raw_url=f"{raw_base_url}/{routeros_relative_path}",
            used_categories=used_categories,
            optional_geoip_categories=optional_geoip_categories,
            self_list_source_url=self_list_url,
            self_list_optional=self_list_optional,
            bundle_list_name=bundle_list_name,
        ),
        encoding="utf-8",
        newline="\n",
    )
    (output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
