#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/crankyoldgit/IRremoteESP8266.git"
CHECKOUT_DIR="${HOME}/irremote"
PINNED_COMMIT="1e2f0f3ef0a93cbf2a8ddb2e95130f8f4c584b3f"
SPLIT_GAP_US=60000

if [ ! -d "${CHECKOUT_DIR}/.git" ]; then
  git init --quiet "${CHECKOUT_DIR}"
  git -C "${CHECKOUT_DIR}" remote add origin "${REPO_URL}"
fi
cd "${CHECKOUT_DIR}"
git fetch --quiet --depth 1 origin "${PINNED_COMMIT}"
git -c advice.detachedHead=false checkout --quiet "${PINNED_COMMIT}"
echo "IRremoteESP8266 at $(git log -1 --format='%h %cd')"

cd tools
make --silent mode2_decode

sed "s/duration > 20000/duration > ${SPLIT_GAP_US}/" mode2_decode.cpp > mode2_decode_long.cpp
python3 - <<'PY'
path = "mode2_decode_long.cpp"
text = open(path).read()
anchor = '          std::cout << std::endl;\n        } else {'
assert text.count(anchor) == 1
text = text.replace(anchor, '          std::cout << std::endl;\n'
                    '          std::cout << "Mesg Desc.     " << IRAcUtils::resultAcToString(&irsend.capture) << std::endl;\n'
                    '        } else {')
if '#include "IRac.h"' not in text:
    text = text.replace('#include "IRutils.h"', '#include "IRutils.h"\n#include "IRac.h"', 1)
open(path, "w").write(text)
PY

g++ -DUNIT_TEST -D_IR_LOCALE_=en-AU -std=gnu++11 -I../src -I../test -c mode2_decode_long.cpp -o mode2_decode_long.o
g++ -pthread IRutils.o IRtimer.o IRsend.o IRrecv.o IRtext.o IRac.o ir_*.o mode2_decode_long.o -o mode2_decode_long
echo "built $(pwd)/mode2_decode_long"
