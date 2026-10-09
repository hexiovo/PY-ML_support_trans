# PYfNIRs host patch prerequisites

These files are host integration deltas for the PY-ML source workbench. They are not a complete host snapshot.

Apply host-integration-ours.patch only to the prepared pre-integration source tree whose file hashes match:

- src/pyml_workbench/gui.py — 983dc1beeb9df61380c31794f299cdac1d63c5f00f59dc4e8f9f1d5525f3857f
- src/pyml_workbench/plugins.py — e515176c9e5233ed8c08eea1e0fafd3be047aeead527297ee13e9b4ef5f99295
- src/pyml_workbench/plugin_dialog.py — 0c8611334e8aba06ac502cca0f52ca00f653deb0719c8736418b93cf70a034ea

The plugins.py and plugin_dialog.py files contain pre-existing generic plugin support and are absent from the clean older Git HEAD. Supply those matching baseline files, together with the matching gui.py baseline, before applying the host delta. Do not apply this delta directly to that clean older HEAD; if the hashes differ, rebase it and rerun the host integration check.

host-reader-fix.patch is a separate change limited to src/pyml_workbench/data.py. It restores numeric negative zero on the XLSX read path after pandas/openpyxl parsing. Its focused regression passed 1/1; CSV parsing is unchanged. The archived regression source is in the RUN evidence at H:/AIcode/HexiPlan/runs/pyfnirs-pyml-converter-20261008-01/evidence/pyml-integration-release-20261009/test_data_reader.py.

The host integration check passed 4/4 on its saved source tree. These patches and this note are for handoff; no host commit was made.
