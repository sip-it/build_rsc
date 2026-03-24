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
    with urllib.request.urlopen(req, timeout=120) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


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


def build_geoip_block(list_name: str, entries: list[str], source_name: str) -> list[str]:
    comment = f"src=github:{source_name}"
    lines = [
        f'/ip firewall address-list remove [find where list="{list_name}" comment="{comment}"]',
        "/ip firewall address-list",
    ]
    lines.extend(f'add list="{list_name}" address={entry} comment="{comment}"' for entry in entries)
    return lines


def build_geosite_block(list_name: str, entries: list[str], source_name: str) -> list[str]:
    comment = f"src=github:{source_name}"
    lines = [
        f'/ip firewall address-list remove [find where list="{list_name}" comment="{comment}"]',
        "/ip firewall address-list",
    ]
    lines.extend(f'add list="{list_name}" address="{entry}" comment="{comment}"' for entry in entries)
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
    generated_at: str,
    release_branch: str,
    combined_raw_url: str,
    dns_adlist_raw_url: str,
    routeros_raw_url: str,
    geoip_source_url: str,
    geosite_source_url: str,
    dns_source_url: str,
    self_list_source_url: str | None,
    self_list_optional: bool,
) -> str:
    self_list_section = ""
    if self_list_source_url:
        self_list_section = f"""
- `self-list.txt` из ветки `self-list` будет автоматически добавлен в `rsc/community-antifilter.rsc`
- источник self-list: `{self_list_source_url}`
- поддерживаются домены, IPv4/IPv6 и CIDR; домены попадут в `geosite-self-list`, IP/CIDR — в `geoip-self-list`
- optional: `{str(self_list_optional).lower()}`
"""

    return f"""# release artifacts

Сгенерировано: `{generated_at}`
Ветка публикации: `{release_branch}`

## Готовые ссылки

- Combined MikroTik RSC: `{combined_raw_url}`
- DNS adlist (`category-ads-all`): `{dns_adlist_raw_url}`
- RouterOS update script: `{routeros_raw_url}`

## Что внутри combined RSC

- `geoip:ru-blocked-community` — `community.lst` сервиса `community.antifilter.download`
- `geosite:antifilter-download-community` — все домены из `community.antifilter.download`
{self_list_section}
## Upstream источники

- geoip source: `{geoip_source_url}`
- geosite source: `{geosite_source_url}`
- dns adlist source: `{dns_source_url}`

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


def main() -> int:
    args = parse_args()
    config_path = pathlib.Path(args.config).resolve()
    output_root = pathlib.Path(args.output).resolve()

    config = load_json(config_path)
    repo = config["repository"]
    sources = config["sources"]
    geoip_base = sources["geoip_base"].rstrip("/")
    geosite_base = sources["geosite_base"].rstrip("/")
    output_cfg = config.get("output", {})
    self_list_cfg = config.get("self_list", {})

    owner = repo["owner"]
    name = repo["name"]
    release_branch = repo.get("release_branch", "release")
    raw_base_url = f"https://raw.githubusercontent.com/{owner}/{name}/{release_branch}"

    combined_relative_path = output_cfg.get("combined_rsc", "rsc/community-antifilter.rsc")
    routeros_relative_path = output_cfg.get("routeros_script", "routeros/rf-update-community.rsc")
    dns_adlist_relative_path = output_cfg.get("dns_adlist", "dns/category-ads-all.txt")
    readme_relative_path = output_cfg.get("readme", "README.md")

    geoip_name = config["geoip"]
    geosite_name = config["geosite"]
    dns_adlist_name = config["dns_adlist"]

    self_list_enabled = bool(self_list_cfg.get("enabled"))
    self_list_branch = self_list_cfg.get("branch", "self-list")
    self_list_path = self_list_cfg.get("path", "self-list.txt")
    self_list_optional = bool(self_list_cfg.get("optional", True))
    self_geoip_list_name = self_list_cfg.get("geoip_list_name", "geoip-self-list")
    self_geosite_list_name = self_list_cfg.get("geosite_list_name", "geosite-self-list")
    self_list_url = None
    if self_list_enabled:
        self_list_url = f"https://raw.githubusercontent.com/{owner}/{name}/{self_list_branch}/{self_list_path}"

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

    manifest: dict = {
        "generated_at": generated_at,
        "repository": repo,
        "sources": sources,
        "combined_rsc": combined_relative_path,
        "routeros_script": routeros_relative_path,
        "dns_adlist": dns_adlist_relative_path,
        "readme": readme_relative_path,
        "categories": {
            "geoip": geoip_name,
            "geosite": geosite_name,
            "dns_adlist": dns_adlist_name,
        },
        "self_list": {
            "enabled": self_list_enabled,
            "url": self_list_url,
            "optional": self_list_optional,
            "geoip_list_name": self_geoip_list_name,
            "geosite_list_name": self_geosite_list_name,
        },
        "files": [
            {
                "kind": "combined",
                "relative_path": combined_relative_path,
                "description": "Combined MikroTik RSC with community antifilter lists and optional self-list.txt",
                "raw_url": f"{raw_base_url}/{combined_relative_path}",
            },
            {
                "kind": "dns_adlist",
                "relative_path": dns_adlist_relative_path,
                "description": "Plain text DNS adlist generated from geosite:category-ads-all",
                "raw_url": f"{raw_base_url}/{dns_adlist_relative_path}",
            },
            {
                "kind": "routeros_script",
                "relative_path": routeros_relative_path,
                "description": "RouterOS example update script",
                "raw_url": f"{raw_base_url}/{routeros_relative_path}",
            },
            {
                "kind": "readme",
                "relative_path": readme_relative_path,
                "description": "Generated README with artifact links",
                "raw_url": f"{raw_base_url}/{readme_relative_path}",
            },
        ],
        "stats": {"geoip": {}, "geosite": {}, "dns_adlist": {}, "self_list": {}},
    }

    combined_lines: list[str] = [
        "# Combined MikroTik RSC generated from runetfreedom lists",
        f"# Generated at {generated_at}",
        "",
    ]

    print(f"build geoip:{geoip_name}")
    geoip_url = f"{geoip_base}/{geoip_name}.txt"
    try:
        geoip_content = fetch_text(geoip_url)
    except urllib.error.URLError as exc:
        raise SystemExit(f"failed to download {geoip_url}: {exc}") from exc

    geoip_source_name = f"geoip-{geoip_name}"
    (raw_dir / f"{geoip_source_name}.txt").write_text(geoip_content, encoding="utf-8", newline="\n")
    geoip_entries: OrderedDict[str, None] = OrderedDict()
    geoip_invalid = 0
    for line in geoip_content.splitlines():
        normalized = normalize_geoip_line(line)
        if normalized is None:
            geoip_invalid += 1
            continue
        geoip_entries.setdefault(normalized, None)

    geoip_list_name = f"geoip-{geoip_name}"
    combined_lines.extend([f"# geoip:{geoip_name}"])
    combined_lines.extend(build_geoip_block(geoip_list_name, list(geoip_entries.keys()), geoip_source_name))
    combined_lines.append("")
    manifest["stats"]["geoip"][geoip_name] = {
        "list_name": geoip_list_name,
        "entries": len(geoip_entries),
        "invalid_or_skipped": geoip_invalid,
        "source_url": geoip_url,
    }

    print(f"build geosite:{geosite_name}")
    geosite_url = f"{geosite_base}/{geosite_name}.txt"
    try:
        geosite_content = fetch_text(geosite_url)
    except urllib.error.URLError as exc:
        raise SystemExit(f"failed to download {geosite_url}: {exc}") from exc

    geosite_source_name = f"geosite-{geosite_name}"
    (raw_dir / f"{geosite_source_name}.txt").write_text(geosite_content, encoding="utf-8", newline="\n")
    geosite_entries: OrderedDict[str, None] = OrderedDict()
    geosite_skipped: dict[str, int] = {}
    for line in geosite_content.splitlines():
        normalized, reason = normalize_geosite_line(line)
        if normalized is None:
            if reason:
                geosite_skipped[reason] = geosite_skipped.get(reason, 0) + 1
            continue
        geosite_entries.setdefault(normalized, None)

    geosite_list_name = f"geosite-{geosite_name}"
    combined_lines.extend([f"# geosite:{geosite_name}"])
    combined_lines.extend(build_geosite_block(geosite_list_name, list(geosite_entries.keys()), geosite_source_name))
    combined_lines.append("")
    manifest["stats"]["geosite"][geosite_name] = {
        "list_name": geosite_list_name,
        "entries": len(geosite_entries),
        "skipped": geosite_skipped,
        "source_url": geosite_url,
    }

    if self_list_enabled and self_list_url:
        print(f"build self_list:{self_list_url}")
        self_list_content = fetch_optional_text(self_list_url, self_list_optional)
        if self_list_content is None:
            manifest["stats"]["self_list"] = {
                "source_url": self_list_url,
                "status": "skipped_optional_missing",
            }
        else:
            (raw_dir / "self-list.txt").write_text(self_list_content, encoding="utf-8", newline="\n")
            self_geoip_entries: OrderedDict[str, None] = OrderedDict()
            self_geosite_entries: OrderedDict[str, None] = OrderedDict()
            self_invalid = 0
            self_geosite_skipped: dict[str, int] = {}

            for line in self_list_content.splitlines():
                geoip_value = normalize_geoip_line(line)
                if geoip_value is not None:
                    self_geoip_entries.setdefault(geoip_value, None)
                    continue

                geosite_value, reason = normalize_geosite_line(line)
                if geosite_value is not None:
                    self_geosite_entries.setdefault(geosite_value, None)
                    continue

                stripped = strip_comments(line.strip())
                if stripped:
                    self_invalid += 1
                    if reason:
                        self_geosite_skipped[reason] = self_geosite_skipped.get(reason, 0) + 1

            if self_geoip_entries:
                combined_lines.extend(["# self-list geoip"])
                combined_lines.extend(build_geoip_block(self_geoip_list_name, list(self_geoip_entries.keys()), "self-list"))
                combined_lines.append("")
            if self_geosite_entries:
                combined_lines.extend(["# self-list geosite"])
                combined_lines.extend(build_geosite_block(self_geosite_list_name, list(self_geosite_entries.keys()), "self-list"))
                combined_lines.append("")

            manifest["stats"]["self_list"] = {
                "source_url": self_list_url,
                "status": "loaded",
                "geoip_list_name": self_geoip_list_name,
                "geosite_list_name": self_geosite_list_name,
                "geoip_entries": len(self_geoip_entries),
                "geosite_entries": len(self_geosite_entries),
                "invalid_or_skipped": self_invalid,
                "geosite_skipped": self_geosite_skipped,
            }

    print(f"build dns_adlist:{dns_adlist_name}")
    dns_adlist_url = f"{geosite_base}/{dns_adlist_name}.txt"
    try:
        dns_adlist_content = fetch_text(dns_adlist_url)
    except urllib.error.URLError as exc:
        raise SystemExit(f"failed to download {dns_adlist_url}: {exc}") from exc

    dns_source_name = f"geosite-{dns_adlist_name}"
    (raw_dir / f"{dns_source_name}.txt").write_text(dns_adlist_content, encoding="utf-8", newline="\n")
    dns_entries: OrderedDict[str, None] = OrderedDict()
    dns_skipped: dict[str, int] = {}
    for line in dns_adlist_content.splitlines():
        normalized, reason = normalize_geosite_line(line)
        if normalized is None:
            if reason:
                dns_skipped[reason] = dns_skipped.get(reason, 0) + 1
            continue
        dns_entries.setdefault(normalized, None)

    manifest["stats"]["dns_adlist"][dns_adlist_name] = {
        "entries": len(dns_entries),
        "skipped": dns_skipped,
        "source_url": dns_adlist_url,
    }

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
            geoip_source_url=geoip_url,
            geosite_source_url=geosite_url,
            dns_source_url=dns_adlist_url,
            self_list_source_url=self_list_url,
            self_list_optional=self_list_optional,
        ),
        encoding="utf-8",
        newline="\n",
    )
    (output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
