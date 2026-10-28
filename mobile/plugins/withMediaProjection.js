const { withMainApplication } = require('@expo/config-plugins');

module.exports = function withMediaProjection(config) {
  return withMainApplication(config, (mod) => {
    let contents = mod.modResults.contents;
    const importLine = 'import com.oney.WebRTCModule.WebRTCModuleOptions';

    if (!contents.includes(importLine)) {
      contents = contents.replace(/^(package .*\n)/m, `$1\n${importLine}\n`);
    }

    const enableProjection = 'WebRTCModuleOptions.getInstance().enableMediaProjectionService = true';
    if (!contents.includes(enableProjection)) {
      const onCreatePattern = /(override fun onCreate\(\)\s*\{\s*\n\s*super\.onCreate\(\))/;
      if (!onCreatePattern.test(contents)) {
        throw new Error('Could not locate MainApplication.onCreate() for MediaProjection setup');
      }
      contents = contents.replace(onCreatePattern, `$1\n    ${enableProjection}`);
    }

    mod.modResults.contents = contents;
    return mod;
  });
};