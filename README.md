# build_rsc

GitHub Actions pipeline для генерации и публикации в ветку `release`:

- `rsc/community-antifilter.rsc`
- `dns/category-ads-all.txt`
- `routeros/rf-update-community.example.rsc`
- `README.md` с готовыми ссылками на артефакты

Что сейчас попадает в `rsc/community-antifilter.rsc`:
- `geoip:ru-blocked-community`
- `geosite:antifilter-download-community`
- `self-list.txt` из ветки `self-list` при наличии

Все записи добавляются в один общий MikroTik address-list:
- `antifilter-community`

Для доменных записей в итоговом `community-antifilter.rsc` автоматически добавляется вариант с `www.`.
Пример:
- `speedtest.net`
- `www.speedtest.net`

Добавлена дедупликация между списками, чтобы избежать повторов в общем файле.
Приоритет при совпадениях:
- community-источники (`geoip:ru-blocked-community`, `geosite:antifilter-download-community`)
- затем `self-list.txt`

То есть если запись уже есть в community-источниках, дубликат из `self-list.txt` в общий `.rsc` повторно не попадёт.

Комментарии у записей формируются динамически по источнику, например:
- `src=github:geoip:ru-blocked-community`
- `src=github:geosite:antifilter-download-community`
- `src=github:self-list`

Отдельно генерируется DNS adlist:
- `dns/category-ads-all.txt`

Дополнительно в конфиге предусмотрен список optional geoip-категорий, который можно включить позже:
- `cloudflare`, `cloudfront`, `facebook`, `fastly`, `google`, `netflix`, `telegram`, `twitter`, `ddos-guard`, `yandex`
