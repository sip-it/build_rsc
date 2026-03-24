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
from typing import Iterable

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
    parser = argparse.ArgumentParser(description="Build MikroTik RSC files from geoip/geosite text lists")
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
    with urllib.request.urlopen(req, timeout=60) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def ensure_clean_dir(path: pathlib.Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def normalize_geoip_line(line: str) -> str | None:
    value = line.strip()
    if not value or value.startswith(COMMENT_PREFIXES):
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
    if raw.startswith(COMMENT_PREFIXES):
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


def write_geoip_rsc(path: pathlib.Path, list_name: str, entries: Iterable[str], source_name: str) -> int:
    count = 0
    comment = f"src=github:{source_name}"
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(f'/ip firewall address-list remove [find where list="{list_name}" comment="{comment}"]\n\n')
        fh.write("/ip firewall address-list\n")
        for entry in entries:
            fh.write(f'add list="{list_name}" address={entry} comment="{comment}"\n')
            count += 1
    return count


def write_geosite_rsc(path: pathlib.Path, list_name: str, entries: Iterable[str], source_name: str) -> int:
    count = 0
    comment = f"src=github:{source_name}"
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(f'/ip firewall address-list remove [find where list="{list_name}" comment="{comment}"]\n\n')
        fh.write("/ip firewall address-list\n")
        for entry in entries:
            fh.write(f'add list="{list_name}" address="{entry}" comment="{comment}"\n')
            count += 1
    return count


def render_routeros_update_script(manifest: dict) -> str:
    lines = [
        '# Example update script for RouterOS',
        '/system script',
        'add name=rf-update-all policy=read,write,test source={',
        '    :local baseUrl "https://raw.githubusercontent.com/<OWNER>/<REPO>/release"',
        '    :local files {',
    ]

    file_entries: list[str] = []
    for item in manifest["files"]:
        file_entries.append(f'        "{item["relative_path"]}";')

    if file_entries:
        lines.extend(file_entries)
    lines.extend(
        [
            '    }',
            '    :foreach f in=$files do={',
            '        :local url ($baseUrl . "/" . $f)',
            '        :local dst ("tmp-" . [:pick $f ([:find $f "/" -1] + 1) [:len $f]])',
            '        :log info ("rf-update-all: downloading " . $url)',
            '        :do {',
            '            /tool fetch url=$url dst-path=$dst keep-result=yes',
            '            :if ([:len [/file find where name=$dst]] = 0) do={',
            '                :error ("download failed: " . $f)',
            '            }',
            '            /import file-name=$dst verbose=yes',
            '            /file remove [find where name=$dst]',
            '            :log info ("rf-update-all: imported " . $f)',
            '        } on-error={',
            '            :log error ("rf-update-all: failed " . $f)',
            '            :if ([:len [/file find where name=$dst]] > 0) do={',
            '                /file remove [find where name=$dst]',
            '            }',
            '        }',
            '    }',
            '}',
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    config_path = pathlib.Path(args.config).resolve()
    output_root = pathlib.Path(args.output).resolve()

    config = load_json(config_path)
    sources = config["sources"]
    geoip_base = sources["geoip_base"].rstrip("/")
    geosite_base = sources["geosite_base"].rstrip("/")

    ensure_clean_dir(output_root)
    rsc_geoip_dir = output_root / "rsc" / "geoip"
    rsc_geosite_dir = output_root / "rsc" / "geosite"
    routeros_dir = output_root / "routeros"
    raw_dir = output_root / "raw"
    for directory in (rsc_geoip_dir, rsc_geosite_dir, routeros_dir, raw_dir):
        directory.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "files": [],
        "stats": {"geoip": {}, "geosite": {}},
    }

    for name in config.get("geoip", []):
        print(f"build geoip:{name}")
        url = f"{geoip_base}/{name}.txt"
        try:
            content = fetch_text(url)
        except urllib.error.URLError as exc:
            raise SystemExit(f"failed to download {url}: {exc}") from exc

        source_name = f"geoip-{name}"
        raw_path = raw_dir / f"{source_name}.txt"
        raw_path.write_text(content, encoding="utf-8", newline="\n")

        entries: OrderedDict[str, None] = OrderedDict()
        invalid = 0
        for line in content.splitlines():
            normalized = normalize_geoip_line(line)
            if normalized is None:
                invalid += 1
                continue
            entries.setdefault(normalized, None)

        list_name = f"geoip-{name}"
        relative_path = f"rsc/geoip/{name}.rsc"
        rsc_path = rsc_geoip_dir / f"{name}.rsc"
        written = write_geoip_rsc(rsc_path, list_name, entries.keys(), source_name)

        manifest["files"].append(
            {
                "kind": "geoip",
                "name": name,
                "list_name": list_name,
                "relative_path": relative_path,
                "source_url": url,
                "entries": written,
            }
        )
        manifest["stats"]["geoip"][name] = {
            "entries": written,
            "invalid_or_skipped": invalid,
            "source_url": url,
        }

    for name in config.get("geosite", []):
        print(f"build geosite:{name}")
        url = f"{geosite_base}/{name}.txt"
        try:
            content = fetch_text(url)
        except urllib.error.URLError as exc:
            raise SystemExit(f"failed to download {url}: {exc}") from exc

        source_name = f"geosite-{name}"
        raw_path = raw_dir / f"{source_name}.txt"
        raw_path.write_text(content, encoding="utf-8", newline="\n")

        entries: OrderedDict[str, None] = OrderedDict()
        skipped: dict[str, int] = {}
        for line in content.splitlines():
            normalized, reason = normalize_geosite_line(line)
            if normalized is None:
                if reason:
                    skipped[reason] = skipped.get(reason, 0) + 1
                continue
            entries.setdefault(normalized, None)

        list_name = f"geosite-{name}"
        relative_path = f"rsc/geosite/{name}.rsc"
        rsc_path = rsc_geosite_dir / f"{name}.rsc"
        written = write_geosite_rsc(rsc_path, list_name, entries.keys(), source_name)

        manifest["files"].append(
            {
                "kind": "geosite",
                "name": name,
                "list_name": list_name,
                "relative_path": relative_path,
                "source_url": url,
                "entries": written,
            }
        )
        manifest["stats"]["geosite"][name] = {
            "entries": written,
            "skipped": skipped,
            "source_url": url,
        }

    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    update_script = render_routeros_update_script(manifest)
    (routeros_dir / "rf-update-all.example.rsc").write_text(update_script, encoding="utf-8", newline="\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())