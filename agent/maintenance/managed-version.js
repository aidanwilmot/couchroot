'use strict';
// Retired managed-package evidence only. Never shipped in native-only packages.
const path = require('path');
const { hash, read } = require('../service/policy');
const HEX = /^[a-f0-9]{64}$/;
function check(value) { if (!value) throw Error('Invalid retired managed package'); }
function managedVersion(payload) {
  const manifest = JSON.parse(read(path.join(payload, 'manifest.json'))),
    files = [];
  for (const name of ['SamsungTvArchiveRoot', 'SamsungTvRootAgent'])
    for (const suffix of ['dll', 'runtimeconfig.json', 'deps.json']) {
      const file = name + '.' + suffix,
        digest = hash(read(path.join(payload, file), 4 * 1024 * 1024));
      check(
        typeof manifest[file] === 'string' &&
          HEX.test(manifest[file]) &&
          digest === manifest[file]
      );
      files.push([file, digest]);
    }
  return hash(JSON.stringify(files));
}
module.exports = { managedVersion };
