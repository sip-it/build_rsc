# release artifacts

Сгенерировано: `2026-03-25T08:49:17.302772+00:00`
Ветка публикации: `release`

## Готовые ссылки

- Combined MikroTik RSC: `https://raw.githubusercontent.com/sip-it/build_rsc/release/rsc/community-antifilter.rsc`
- DNS adlist (`category-ads-all`): `https://raw.githubusercontent.com/sip-it/build_rsc/release/dns/category-ads-all.txt`
- RouterOS update script: `https://raw.githubusercontent.com/sip-it/build_rsc/release/routeros/rf-update-community.rsc`

## Что входит в combined RSC

- общий list name: `antifilter-community`
- `geoip:ru-blocked-community`
- `geosite:antifilter-download-community`
- `self-list`

## self-list

- источник: `https://raw.githubusercontent.com/sip-it/build_rsc/self-list/self-list.txt`
- optional: `true`
- строки с доменами и IP/CIDR добавляются в общий list `antifilter-community`

## Дополнительные geoip-категории (поддерживаются конфигом)

Сейчас они не включены в итоговый `.rsc`, но их можно включить в `config/lists.json`.

- `geoip:cloudflare`
- `geoip:cloudfront`
- `geoip:facebook`
- `geoip:fastly`
- `geoip:google`
- `geoip:netflix`
- `geoip:telegram`
- `geoip:twitter`
- `geoip:ddos-guard`
- `geoip:yandex`

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
