# CardDemo legacy reference environment (GnuCOBOL on GCP)

A running "before" system for testing the migration studio: CardDemo's batch COBOL
programs on a small Compute Engine VM, with VSAM replaced by GnuCOBOL indexed files.

## Deploy
1. Install the gcloud CLI and run `gcloud auth login`.
2. `PROJECT_ID=<your-project> ./provision.sh`   (optional: `ZONE=`, `VM=`)
   Creates an e2-medium Debian 12 VM, installs GnuCOBOL, clones CardDemo, compiles, loads data.
3. Run the nightly flow:
   `gcloud compute ssh carddemo-legacy --command 'sudo /opt/carddemo-env/run-batch.sh'`

Outputs land in `/opt/carddemo-env/out`; data files in `/opt/carddemo-env/data`.
Stop the VM when idle: `gcloud compute instances stop carddemo-legacy`.

## What runs
Built: CBACT01C-04C, CBCUS01C, CBTRN01C-03C, COBSWAIT. `run-batch.sh` runs POSTTRAN (CBTRN02C)
then INTCALC (CBACT04C). Verified in WSL (GnuCOBOL 3.2): 300 posted, 38 rejected (rc=4 is the
program's normal "had rejects" code).

## Not covered (needs a mainframe runtime)
- CICS online programs (CO*C, BMS screens), IMS, Db2, MQ modules: not runnable here. Use them as
  static source for the studio to analyse.
- CBSTM03A/B (statements) use z/OS control blocks; CBEXPORT/CBIMPORT not wired up.

## Emulation notes
- `-fsign=EBCDIC` keeps the sample data's signed overpunch (`{`, `A-I`, `}`, `J-R`) valid.
- JCL DD names map to env vars `DD_<name>` (see run-batch.sh); IDCAMS/REPRO is replaced by `load-data.sh`.
- `stubs/CEE3ABD.cbl` stands in for the IBM LE abend call; `stubs/RUNCBACT04C.cbl` supplies the JCL PARM.
- `test-local-wsl.sh` rebuilds and reloads inside WSL for local testing.
