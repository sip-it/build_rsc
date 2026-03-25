# Generated release files

Полезные ссылки:

- community-antifilter.rsc: `https://raw.githubusercontent.com/sip-it/build_rsc/release/rsc/community-antifilter.rsc`
- dns adlist category-ads-all.txt: `https://raw.githubusercontent.com/sip-it/build_rsc/release/dns/category-ads-all.txt`
- RouterOS update script example: `https://raw.githubusercontent.com/sip-it/build_rsc/release/routeros/rf-update-community.rsc`

Содержимое `community-antifilter.rsc`:
- geoip:ru-blocked-community
- geosite:antifilter-download-community
- self-list.txt из ветки `self-list`, если файл существует

Особенности сборки:
- geosite:category-ads-all не включается в общий `.rsc`, только в отдельный DNS adlist
- доменные записи в общем `.rsc` дополняются вариантом с `www.`
- `www.` не добавляется для доменов, начинающихся с `api.` или `cdn.`
- при дедупликации приоритет у community-источников, потом self-list
