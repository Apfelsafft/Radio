#!/bin/sh
# Rebuild yapaia_beat/.../www/sendspin.js from the pinned versions in
# package-lock.json.  The bundle is committed, so the add-on build needs no
# Node.js; run this only to update sendspin-js.
set -e
cd "$(dirname "$0")"
npm ci --no-audit --no-fund
OUT=../../yapaia_beat/rootfs/opt/yapaia/integration/yapaia_beat/www
npx esbuild entry.js --bundle --format=esm --minify --target=es2020 \
  --legal-comments=eof --outfile="$OUT/sendspin.js"
{
  echo "Third-party software bundled in sendspin.js"
  echo "============================================"
  for p in @sendspin/sendspin-js @noble/ciphers @noble/curves @noble/hashes opus-encdec; do
    v=$(node -p "require('./node_modules/$p/package.json').version")
    echo; echo "---- $p $v ----"; echo
    cat node_modules/$p/LICENSE* 2>/dev/null
  done
} > "$OUT/sendspin.LICENSES.txt"
