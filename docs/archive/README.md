# Decision archive

Dated decision records for this repository live in `docs/archive/archive.zip`.
The archive is created, read, and written only through `pb archive`:

```bash
pb archive list
pb archive read <ID>
pb archive add <record>
```

Records sit at the archive root; retired files live under its `deprecated/`
namespace. No `archive.zip` is checked in until the first record is added, and
no fabricated archive belongs in the tree. Current state stays in
`docs/breakdown/`; the archive is history only.
