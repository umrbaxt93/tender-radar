# E-Birja fixtures

`export_SYNTHETIC.csv` is a **synthetic** stand-in for an E-Birja cabinet export, written so the
importer and its tests have something to run against. It is not real procurement data and must
never be presented as a real result.

No real export file was available when the importer was written, and CLAUDE.md forbids logging
in to ebirja.uz to fetch one, so the column wordings in `radar/source/ebirja_export_mapping.yaml`
are **candidates, not observed headers**. Run this against a real export first:

    radar import-ebirja-export --inspect <file>

It prints the file's own headers and what each field matched. Add any real wording the mapping
missed to that YAML -- no code change is needed.
