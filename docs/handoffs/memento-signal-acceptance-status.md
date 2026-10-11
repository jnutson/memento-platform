# Memento Signal acceptance status

Recorded: 2026-10-10. This is an interim acceptance record; it does not certify
MVP completion.

## Approved carrying-cost assumption

- Annual carrying-cost rate: `0.25` (25% of inventory cost per year).
- Configuration version: `synthetic-toy-retail-benchmark-v1`.
- Intended use: synthetic toy-retail demonstration. This is an assumed benchmark,
  not a measured customer rate.
- The rate remains an explicit Memento CLI input and part of the signal manifest's
  configuration and content identity.

## Full-scale execution evidence

The validated Synthetic Data handback reports commit
`67fa902d339daf0a07f8e5d0ab1e748fc7974244` and simulation
`4ead8d45af58002bfc8a30c0d6241e92019f6ab4e917d7df7e379621788bfd5a`.
Its initial, evaluation, and archive release cutoffs are respectively
`2027-01-30T12:00:00Z`, `2027-02-27T12:00:00Z`, and
`2028-01-29T12:00:00Z`.

Initial-release ingestion completed in 211.46 seconds and published canonical
dataset `mds_0779df6554b9230828803ece846ebbfa454a8e1317b77ba31af03395b3dd929a`
with ten tables. Maximum resident set was 3,277,914,112 bytes.

Prediction completed in 228.20 seconds and published prediction set
`mps_c1d921fd006f0d11f219ae3e424c73d33d40790d50ff04a8d07710941885ed7d`.
Maximum resident set was 9,330,753,536 bytes; reported peak memory footprint was
23,610,941,680 bytes.

Signal generation was launched with the approved rate and version. At a measured
7 hours 49 minutes it was still CPU-active, with no final signal-set publication.
Its completion, candidate counts, top-ten composition, and file hashes are not yet
verified. CPU activity alone does not establish how much work remains.

## Remaining acceptance work

- Complete signal publication and inspect counts, ranking, and evidence integrity.
- Verify natural mixed top-ten composition and the required per-type coverage.
- Establish replay evidence for full-scale signal generation.
- Ingest the evaluation release and evaluate the frozen initial predictions.
- Ingest the archive release and verify archive/replay behavior.
- Verify API/UI behavior against the full-scale published outputs.
- Address signal-generation scalability: `run_signals` queries history, calendar,
  and inbound data inside its observation loop. Bulk preparation should be tested
  for equivalent calculations and materially improved runtime.

Generated datasets remain under the ignored local `data/` directory and are not
part of this delivery. The Synthetic Data repository is read-only from Memento.
