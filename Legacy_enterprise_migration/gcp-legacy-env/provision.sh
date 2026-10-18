#!/usr/bin/env bash
# Run from a machine with gcloud installed and authenticated (gcloud auth login).
# Usage: PROJECT_ID=my-project ./provision.sh
set -euo pipefail
: "${PROJECT_ID:?set PROJECT_ID}"
ZONE="${ZONE:-us-central1-a}"
VM="${VM:-carddemo-legacy}"
cd "$(dirname "$0")"

gcloud config set project "$PROJECT_ID"
gcloud services enable compute.googleapis.com

gcloud compute instances create "$VM" --zone "$ZONE" \
  --machine-type e2-medium \
  --image-family debian-12 --image-project debian-cloud \
  --boot-disk-size 20GB \
  --metadata-from-file startup-script=bootstrap-vm.sh

echo "Waiting for SSH and package install..."
for i in $(seq 1 40); do
  gcloud compute ssh "$VM" --zone "$ZONE" --command 'test -f /opt/carddemo-env/.packages-ready' 2>/dev/null && break
  sleep 15
done

gcloud compute scp --zone "$ZONE" --recurse build.sh load-data.sh run-batch.sh stubs "$VM":/tmp/
gcloud compute ssh "$VM" --zone "$ZONE" --command '
  sudo cp -r /tmp/build.sh /tmp/load-data.sh /tmp/run-batch.sh /tmp/stubs /opt/carddemo-env/ &&
  sudo chmod +x /opt/carddemo-env/*.sh &&
  sudo /opt/carddemo-env/build.sh && sudo /opt/carddemo-env/load-data.sh'

echo "Done. Run the batch flow with:"
echo "  gcloud compute ssh $VM --zone $ZONE --command 'sudo /opt/carddemo-env/run-batch.sh'"
