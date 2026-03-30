# Generated release files

Полезные ссылки:

- community-antifilter.rsc: `https://raw.githubusercontent.com/sip-it/build_rsc/release/rsc/community-antifilter.rsc`
- dns adlist category-ads-all.txt: `https://raw.githubusercontent.com/sip-it/build_rsc/release/dns/category-ads-all.txt`
- RouterOS update address-list: `https://raw.githubusercontent.com/sip-it/build_rsc/release/routeros/rf-update-community.example.rsc`
- RouterOS update dns adlist: `https://raw.githubusercontent.com/sip-it/build_rsc/release/routeros/rf-update-dns-adlist.example.rsc`
- RouterOS setup 1d: `https://raw.githubusercontent.com/sip-it/build_rsc/release/routeros/rf-setup-1d.example.rsc`
- RouterOS setup 7d: `https://raw.githubusercontent.com/sip-it/build_rsc/release/routeros/rf-setup-7d.example.rsc`

Содержимое `community-antifilter.rsc`:
- geoip:ru-blocked-community
- geosite:antifilter-download-community
- self-list.txt из ветки `self-list`, если файл существует

Особенности сборки:
- geosite:category-ads-all не включается в общий `.rsc`, только в отдельный DNS adlist
- доменные записи в общем `.rsc` дополняются вариантом с `www.`
- для `api.*` и `cdn.*` вариант `www.` не добавляется
- при дедупликации приоритет у community-источников, потом self-list
- для self-list используются разные comments для geoip и geosite
