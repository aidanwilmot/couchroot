# README screenshots

Generated from the repository's actual launcher with synthetic browser fixtures:

```sh
npm ci
npx playwright install chromium
npm run screenshots
```

`launcher.png` is the `many` scenario, `settings.png` the `settings` scenario,
and `compact.png` the `compact` scenario. Source captures are under the ignored
`test-results/screenshots/` directory. Images are 1920×1080. No live TV, telemetry,
network configuration or private account data is used in these captures.
