# build_rsc

GitHub Actions pipeline для генерации и публикации в ветку `release`:

- `rsc/community-antifilter.rsc`
- `dns/category-ads-all.txt`
- `routeros/rf-update-community.example.rsc`
- `README.md` с готовыми ссылками на артефакты

Что сейчас попадает в `rsc/community-antifilter.rsc`:
- `geoip:ru-blocked-community`
- `geosite:antifilter-download-community`
- `geosite:category-ads-all`
- `self-list.txt` из ветки `self-list` при наличии

Все записи добавляются в один общий MikroTik address-list:
- `antifilter-community`

Комментарии у записей формируются динамически по источнику, например:
- `src=github:geoip:ru-blocked-community`
- `src=github:geosite:antifilter-download-community`
- `src=github:geosite:category-ads-all`
- `src=github:self-list`

Дополнительно в конфиге предусмотрен список optional geoip-категорий, который можно включить позже:
- `cloudflare`, `cloudfront`, `facebook`, `fastly`, `google`, `netflix`, `telegram`, `twitter`, `ddos-guard`, `yandex`
