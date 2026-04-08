# build_rsc

Сборка артефактов для MikroTik/RouterOS и DNS adlist из runetfreedom.

## Что генерируется в ветку `release`

- `rsc/community-antifilter.rsc`
- `dns/category-ads-all.txt`
- `routeros/rf-update-community.example.rsc`
- `routeros/rf-update-dns-adlist.example.rsc`
- `routeros/rf-setup-1d.example.rsc`
- `routeros/rf-setup-7d.example.rsc`
- `README.md`
- `manifest.json`

## Что входит в `community-antifilter.rsc`

Общий MikroTik address-list с именем `antifilter-community`.

Источники:

- `geoip:ru-blocked-community`
- `geosite:antifilter-download-community`
- `self-list.txt` из ветки `self-list`, если файл существует

`geosite:category-ads-all` в общий `.rsc` не включается.

Доменные записи в этом файле оптимизированы под downstream-сценарий, где RouterOS
дальше использует `DNS static FWD` с `match-subdomain=yes`:

- `www.` отдельно не дублируется
- если в наборе уже есть базовый домен, дочерние поддомены в итоговом `.rsc` удаляются как избыточные
- `raw/*` при этом не переписывается и остается снимком исходных данных

## Что входит в DNS adlist

Отдельный файл `dns/category-ads-all.txt`.

Источник:

- `geosite:category-ads-all`

## Особенности

- для доменных записей не добавляется отдельный вариант с `www.`
- поддомены, включая `www.*`, обрабатываются на RouterOS через `DNS static FWD` c `match-subdomain=yes`
- итоговый `community-antifilter.rsc` тоже упрощается по этой модели
- есть дедупликация между источниками
- приоритет у community-источников, потом `self-list`
- для `self-list` используются разные comments:
  - `src=github:self-list:geoip`
  - `src=github:self-list:geosite`
- RouterOS update script очищает только `dynamic=no` записи, чтобы не падать на динамических DNS-resolved entries
- `raw/*` сохраняет исходные upstream/self-list данные без упрощения

## RouterOS

В release будут готовые файлы:

- `rf-update-community.example.rsc` — обновление address list
- `rf-update-dns-adlist.example.rsc` — регистрация/reload DNS adlist
- `rf-setup-1d.example.rsc` — scheduler на 1 день
- `rf-setup-7d.example.rsc` — scheduler на 7 дней

## Пример `self-list.txt`

```text
example.com
speedtest.net
1.2.3.4
10.20.30.0/24
api.example.org
cdn.example.org
```
