const { withAndroidManifest } = require('@expo/config-plugins');

// Android blocks plain HTTP to the local backend by default; the dev backend is on a
// trusted LAN with no public exposure, so cleartext is acceptable here.
module.exports = function withCleartextTraffic(config) {
  return withAndroidManifest(config, (mod) => {
    const application = mod.modResults.manifest.application?.[0];
    if (application) {
      application.$['android:usesCleartextTraffic'] = 'true';
    }
    return mod;
  });
};
