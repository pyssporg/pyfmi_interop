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
