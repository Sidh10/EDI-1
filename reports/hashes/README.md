# Output hash records

Committed SHA-256 records of regenerated outputs. The outputs themselves (`reports/tables/`,
`data/`) are gitignored; these records are the committed byte-level reference they can be checked
against. Every `sha256` is of the **exact file bytes**, the same definition the manuscript manifest
uses (`manuscript.py`: `hashlib.sha256(path.read_bytes())`).

| file | covers |
|---|---|
| `E1-E3.sha256.csv` | the 20 E1–E3 result tables written by `kc audit` |
| `events_parquet.sha256.csv` | `data/processed/events.parquet` (built by `kc audit`) |
| `data_raw.sha256.csv` | every file in `data/raw/` after `kc ingest` |

**Columns** (`E1-E3.sha256.csv`):
- `experiment`, `path`, `sha256`, `bytes`;
- `rows`, `cols`: informational, from `pandas.read_csv(..., float_precision="round_trip")`;
- `eol`: the line endings in the file bytes. Tables written on Windows are CRLF, which is part of the
  hash;
- `git_commit`: the commit the outputs were **computed** at, from the run's provenance sidecar;
- `config_hash`, `python`, `platform`, `hashed_utc`;
- `status`: `reproduced` if the hash equals an earlier committed hash (the manuscript manifest's
  `source_sha256`), or `first-recorded` if no earlier reference existed.

**Content hash of `events.parquet`.** `content_sha256` does not depend on the parquet writer: not on
encoding, compression, row-group layout, `created_by` or key-value metadata. It is the SHA-256 over,
for each column in schema order:

```
name (UTF-8) | 0x00 | Arrow type string | 0x00 | row count (uint64 LE)
validity: one byte per row (1 = valid, 0 = null)
values, one per row:
  double -> IEEE-754 binary64 little-endian; NaN canonicalised to 0x7FF8000000000000; null -> 8 zero bytes
  int64  -> int64 little-endian;           null -> 8 zero bytes
  bool   -> one byte 0/1;                  null -> 0
  string -> uint32 LE UTF-8 byte length, then the bytes; null -> 0xFFFFFFFF
```

- Row order is the stored order.
- The pandas schema metadata is excluded.
- Checked when first recorded: rewriting the same table with gzip compression and 50,000-row groups,
  or with no compression, 10,000-row groups and no dictionary encoding, changed `sha256_file_bytes`
  but left `content_sha256` unchanged.

`events.parquet` holds **one row per CDM**, not per event: 162,634 train and 24,484 test CDM rows
(187,118 in total) across 15,321 distinct `event_uid`.
