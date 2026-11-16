# bmw-cpo-watch database backups

Daily backup of the watcher SQLite database, committed by the morning hunt run.

- `bmwcpo.sqlite.gz.b64` is the database, gzipped then base64-encoded (the
  snapshot push only accepts UTF-8 text, so the binary is stored encoded).
  The ephemeral `raw_responses` API cache is dropped before the backup;
  everything else is kept: listings, price_history, search_hits, runs,
  search_stats.
- The live `data/` directory (API token, logs) is never committed.

Restore:

```bash
base64 -d bmwcpo.sqlite.gz.b64 | gunzip > bmwcpo.sqlite
sqlite3 bmwcpo.sqlite "PRAGMA integrity_check;"
```
