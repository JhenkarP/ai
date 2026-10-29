const fs = require('fs');
const path = require('path');
const { withDangerousMod } = require('@expo/config-plugins');

// react-native-webrtc references optional native codec classes (AV1/Dav1d, HEVC, etc.) that
// are not bundled; R8 fails the whole release build over them unless told they are expected.
const RULES = `
-dontwarn org.webrtc.**
-keep class org.webrtc.** { *; }
`;

module.exports = function withWebrtcProguardRules(config) {
  return withDangerousMod(config, [
    'android',
    (mod) => {
      const filePath = path.join(mod.modRequest.platformProjectRoot, 'app', 'proguard-rules.pro');
      const contents = fs.readFileSync(filePath, 'utf8');
      if (!contents.includes('org.webrtc.**')) {
        fs.writeFileSync(filePath, `${contents}\n${RULES}`);
      }
      return mod;
    },
  ]);
};
