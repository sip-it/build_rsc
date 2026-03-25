# build_rsc

Сборка артефактов для MikroTik/RouterOS и DNS adlist из runetfreedom.

Что генерируется в ветку `release`:

- `rsc/community-antifilter.rsc`
- `dns/category-ads-all.txt`
- `routeros/rf-update-community.example.rsc`
- `README.md`
- `manifest.json`

## Что входит в `community-antifilter.rsc`

Общий MikroTik address-list с именем:

```text
antifilter-community
```

Источники:

- `geoip:ru-blocked-community`
- `geosite:antifilter-download-community`
- `self-list.txt` из ветки `self-list`, если файл существует

`geosite:category-ads-all` в общий `.rsc` не включается.

## Что входит в DNS adlist

Отдельный файл:

```text
dns/category-ads-all.txt
```

Источник:

- `geosite:category-ads-all`

## Особенности

- для доменных записей в `community-antifilter.rsc` добавляется вариант с `www.`
- `www.` не добавляется для доменов, начинающихся с `api.` или `cdn.`
- есть дедупликация между источниками
- приоритет у community-источников, потом `self-list`
- для `self-list` используются разные comments:
  - `src=github:self-list:geoip`
  - `src=github:self-list:geosite`

Это сделано, чтобы RouterOS не удалял geoip-записи `self-list` при импорте блока geosite.

## Пример `self-list.txt`

```text
example.com
speedtest.net
api.example.com
cdn.example.com
1.2.3.4
10.20.30.0/24
```

В итоговом `community-antifilter.rsc` домены будут добавлены как:

```text
example.com
www.example.com
speedtest.net
www.speedtest.net
api.example.com
cdn.example.com
```

## Полезные файлы после сборки

- `rsc/community-antifilter.rsc` — общий MikroTik RSC
- `dns/category-ads-all.txt` — DNS adlist
- `routeros/rf-update-community.example.rsc` — пример update-скрипта для RouterOS
