#!/bin/bash

echo "Downloading ensime server archive"
ENSIME_VERSION=ensime_2.10.0-SNAPSHOT-0.9.4
curl -OL# https://github.com/downloads/sublimescala/ensime/$ENSIME_VERSION.tar.gz
echo "Extracting ensime server"
tar xzf $ENSIME_VERSION.tar.gz
rm $ENSIME_VERSION.tar.gz
echo "All done."
