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

cp --update --archive  $base/../*.py  $dest/skyview
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
echo Note:   The first deployment, the app  would not work, returning blank page
echo         with errors in developer console suggesting failure in opening websockets.
echo Action: In gcloud service dashboard, add environment variable BOKEH_ALLOW_WS_ORIGIN,
echo         set it to the public hostname of the deployed service, and deploy again.

