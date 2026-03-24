# build_rsc

GitHub Actions pipeline для генерации и публикации в ветку `release`:

- `rsc/community-antifilter.rsc`
- `dns/category-ads-all.txt`
- `routeros/rf-update-community.rsc`
- `README.md` с готовыми ссылками на артефакты

Дополнительно поддерживается кастомный источник `self-list.txt` из ветки `self-list`.
Во время сборки его содержимое автоматически добавляется в `rsc/community-antifilter.rsc`:
- домены -> `geosite-self-list`
- IP/CIDR -> `geoip-self-list`

Если `self-list.txt` ещё не создан, сборка не упадёт: источник отмечен как optional.
