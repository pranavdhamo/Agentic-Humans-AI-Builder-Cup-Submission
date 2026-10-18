set -e
B=/opt/carddemo-env; rm -rf $B; mkdir -p $B
W=/mnt/d/AI_Builder_cup/Legacy_enterprise_migration
cp -r $W/gcp-legacy-env/build.sh $W/gcp-legacy-env/load-data.sh $W/gcp-legacy-env/run-batch.sh $W/gcp-legacy-env/stubs $B/
sed -i 's/\r$//' $B/*.sh
ln -s $W/aws-mainframe-modernization-carddemo $B/carddemo
chmod +x $B/*.sh
$B/build.sh; echo ======; $B/load-data.sh
