#!/bin/sh

proj_root=../../../

base=`dirname $0`
dest=$1

if [ "$dest" == "" ]; then
    dest=$base/../../../build/tess-skyview
fi

set -e

mkdir -p $dest
mkdir -p $dest/skyview

cp --update --archive  $base/../main.py  $dest/skyview
cp --update --archive  $base/*  $dest
cp --update --archive  $base/.*  $dest

ls -l $dest/

echo
echo Sources assembled. You can do the following for actual deployment:
echo
echo cd $dest
echo "# sanity test locally"
echo bokeh serve --show skyview
echo "# actual deployment with Google Cloud SDK"
echo gcloud run deploy --source .
echo
echo Note: The first deployment would fail.
echo       In gcloud service dashboard,
echo       add environment variable BOKEH_EXTERNAL_HOSTNAME,
echo       set it to the public hostname of the deployed service, and deploy again.

