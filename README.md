
GitHub Actions pipeline для генерации MikroTik `.rsc` файлов из:

- `runetfreedom/russia-blocked-geoip` (`release/text/*.txt`)
- `runetfreedom/russia-blocked-geosite` (`release/*.txt`)

Что делает pipeline:

1. скачивает plain text категории,
2. собирает `dist/rsc/geoip/*.rsc` и `dist/rsc/geosite/*.rsc`,
3. публикует результат в ветку `release`,
4. кладёт `dist/routeros/rf-update-all.example.rsc` и `dist/manifest.json`.
