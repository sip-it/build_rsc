# release artifacts

Сгенерировано: `2026-03-25T07:31:36.126226+00:00`
Ветка публикации: `release`

## Готовые ссылки

- Combined MikroTik RSC: `https://raw.githubusercontent.com/sip-it/build_rsc/release/rsc/community-antifilter.rsc`
- DNS adlist (`category-ads-all`): `https://raw.githubusercontent.com/sip-it/build_rsc/release/dns/category-ads-all.txt`
- RouterOS update script: `https://raw.githubusercontent.com/sip-it/build_rsc/release/routeros/rf-update-community.rsc`

## Что внутри combined RSC

- `geoip:ru-blocked-community` — `community.lst` сервиса `community.antifilter.download`
- `geosite:antifilter-download-community` — все домены из `community.antifilter.download`

- `self-list.txt` из ветки `self-list` будет автоматически добавлен в `rsc/community-antifilter.rsc`
- источник self-list: `https://raw.githubusercontent.com/sip-it/build_rsc/self-list/self-list.txt`
- поддерживаются домены, IPv4/IPv6 и CIDR; домены попадут в `geosite-self-list`, IP/CIDR — в `geoip-self-list`
- optional: `true`

## Upstream источники

- geoip source: `https://raw.githubusercontent.com/runetfreedom/russia-blocked-geoip/release/text/ru-blocked-community.txt`
- geosite source: `https://raw.githubusercontent.com/runetfreedom/russia-blocked-geosite/release/antifilter-download-community.txt`
- dns adlist source: `https://raw.githubusercontent.com/runetfreedom/russia-blocked-geosite/release/category-ads-all.txt`

## MikroTik CHR

Импорт напрямую:

```rsc
/tool fetch url="https://raw.githubusercontent.com/sip-it/build_rsc/release/rsc/community-antifilter.rsc" dst-path=community-antifilter.rsc keep-result=yes
/import file-name=community-antifilter.rsc verbose=yes
/file remove [find where name=community-antifilter.rsc]
```

Или импортируй готовый update-script:

```rsc
/tool fetch url="https://raw.githubusercontent.com/sip-it/build_rsc/release/routeros/rf-update-community.rsc" dst-path=rf-update-community.rsc keep-result=yes
/import file-name=rf-update-community.rsc verbose=yes
```
