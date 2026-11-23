---
id: INFO-011
type: info
title: Attribute semantics
summary: The composition layer extracts plain attribute values and interop owns every timing, type, identity and capacity decision.
date: 2026-11-22
status: current
---

# Attribute semantics

`core/attributes.py` is the one home for the rules that turn authored
attribute values into interface decisions; it receives plain strings and
numbers and never a parser object or a dialect name.

- **Extraction boundary:** `pyfmi_sysml.parse` reads values off the parser-free
  reduction, merges a component's and a port's attributes, and hands the plain
  mappings over. It does not re-derive spelling, precedence, types or identity.
- **Timing spelling:** `step_size_s`/`step_size`, then `period_s`/`period`, then
  `rate_hz`/`rate`; `period` is seconds at or below 1 and hertz above 1.
- **Step precedence:** an explicit override wins, then the system scope, then
  each component, then each port; no authored value means the 1 kHz default.
- **Signal rate:** an explicit rate key wins over the period and step spellings
  in the merged attributes, so a port overrides its component.
- **Types and identity:** the FMI type and causality maps, the string capacity
  (256 bytes), the C-identifier sanitizer and the model-name fallback live
  here. `adapter_model.py` imports the same type map and capacity instead of
  defining a second copy.
- **Projection:** `signal_from_values` builds the IR signal, including the
  fixed string capacity and the provisional value reference fallback.
- **Refusal:** a non-numeric, non-positive or unsupported value raises
  `ValueError` here, before generation.
