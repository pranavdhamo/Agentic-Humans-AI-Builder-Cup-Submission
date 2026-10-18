# Restart the CardDemo legacy VM

- Project: `project-4e2a7a69-6910-497e-930`
- VM: `carddemo-legacy`
- Zone: `us-central1-a`

The VM keeps its disk (compiled programs and loaded data) while stopped. You only pay for disk storage until you start it again.

## Option 1: GCP Console (browser)
1. Open https://console.cloud.google.com/compute/instances?project=project-4e2a7a69-6910-497e-930
2. Tick the checkbox next to `carddemo-legacy` and click **Start / Resume** at the top. Confirm.
3. Wait for the green check, then click **SSH** on the row to open a terminal.

## Option 2: gcloud CLI
```bash
gcloud config set project project-4e2a7a69-6910-497e-930
gcloud compute instances start carddemo-legacy --zone us-central1-a
```
Wait about 30 seconds for boot, then connect:
```bash
gcloud compute ssh carddemo-legacy --zone us-central1-a
```

## Commands to paste in the VM terminal (Console SSH window)
```bash
cd /opt/carddemo-env
ls -l data out                  # loaded data files and batch outputs
sudo head -c 600 out/SYSTRAN.ps   # posted transactions
sudo head -c 600 out/DALYREJS.ps  # rejected transactions
sudo ./run-batch.sh             # re-run the whole nightly flow
```
The output files are fixed-width records with no newlines, so use `head -c` or `wc -c` instead of `wc -l`.

## Run the batch flow
Inside the VM (SSH window):
```bash
cd /opt/carddemo-env
sudo ./run-batch.sh        # POSTTRAN (CBTRN02C) -> INTCALC (CBACT04C)
ls -l out                  # SYSTRAN.ps = posted, DALYREJS.ps = rejected
```
Or from your own terminal, without opening a shell:
```bash
gcloud compute ssh carddemo-legacy --zone us-central1-a --command 'sudo /opt/carddemo-env/run-batch.sh'
```
Expected: 300 transactions processed, 38 rejected, `rc=4` for POSTTRAN (normal "had rejects" code), `rc=0` for INTCALC.

## Copy outputs to your machine
```bash
gcloud compute scp --zone us-central1-a --recurse carddemo-legacy:/opt/carddemo-env/out ./out
```

## Stop it again when idle
```bash
gcloud compute instances stop carddemo-legacy --zone us-central1-a
```
Or in the Console: tick the VM and click **Stop**.

## Notes
- The external IP changes after a stop/start. Use `gcloud compute ssh` or the Console SSH button instead of a saved IP.
- Delete everything when finished: `gcloud compute instances delete carddemo-legacy --zone us-central1-a`
- If you re-run `provision.sh` from Windows, convert the scripts to LF first: `sed -i 's/\r$//' *.sh stubs/*.cbl`
