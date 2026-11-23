<!-- GENERATED FILE — do not edit. Regenerate with `pb registers`. -->

# Decision Stream

Flat, dated history of every committed design choice. Current state lives
in the layer leaves named by each record's `state:` field.

Records live in the cold-storage archive; extract one with `pb archive read <ID>`.

## By Layer

### Intent

- **ID-001** — Wire-only remit · accepted · 2026-11-19 · `ID-001`
  The repository owns one versioned byte contract for the model interface and nothing above it.
- **ID-002** — Adapter models and registered wire seams · accepted · 2026-11-19 · `ID-002`
  The repository generates adapter models and owns serialization and transport as registered seams, without taking on semantics.
- **ID-003** — The FMI layer is generated, the IR is the wire projection · accepted · 2026-11-19 · `ID-003`
  The adapter FMU takes its FMI C interface, headers and modelDescription from pyfmi_sysml2; pyfmi_interop implements the model hooks and owns the wire plane, with FMI value references and wire field numbers as separate namespaces.
- **ID-004** — The adapter is step-free · accepted · 2026-11-19 · `ID-004`
  An adapter executes once per fmi2DoStep and never schedules, so step size leaves its wire identity, its model description and its build inputs; the realtime model keeps the fixed step.
- **ID-005** — Core/SysML split, one parse, one FMI facade per artifact · accepted · 2026-11-20 · `ID-005`
  The Python layer splits into a SysML-free core and a SysML boundary; ModelSpec and BuildConfig are the public contract, ModelDefinition stays internal, SysML is parsed once, and each artifact owns one FMI facade.
- **ID-007** — Lower packages are SysML-free · accepted · 2026-11-22 · `ID-007`
  Artifact-family packages generate from an interface model without SysML, one composition layer per family owns ingestion, and the SysML vocabulary is a dependency-free artifact.

### Architecture

- **ID-006** — The Reduction is the only SysML hand-off; typed starts on Variable · accepted · 2026-11-20 · `ID-006`
  SysML is reduced once into a parser-free Reduction that carries typed starts and authored attributes, and the adapter never re-resolves the export unit.
- **ID-008** — One published GUID per adapter artifact · accepted · 2026-11-22 · `ID-008`
  The adapter's published GUID is authoritative and its wire model reuses it, so fingerprinting hashes one identity.
- **ID-009** — Public adapter seam and interop-owned attribute semantics · accepted · 2026-11-22 · `ID-009`
  The adapter facade publishes writer, guard and selection, attribute semantics live in interop, and definitions carry no export policy.
