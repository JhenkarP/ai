const path = require('path');
const dotenv = require('dotenv');
const { withGradleProperties } = require('@expo/config-plugins');

const withReleaseMinificationDisabled = (config) =>
  withGradleProperties(config, (config) => {
    const minifyProperty = config.modResults.find(
      (property) => property.key === 'android.enableMinifyInReleaseBuilds',
    );

    if (minifyProperty) {
      minifyProperty.value = 'false';
    } else {
      config.modResults.push({
        type: 'property',
        key: 'android.enableMinifyInReleaseBuilds',
        value: 'false',
      });
    }

    return config;
  });

dotenv.config({ path: path.resolve(__dirname, '../.env') });

module.exports = ({ config }) => {
  const mapsOptions = {};
  if (process.env.GOOGLE_MAPS_ANDROID_API_KEY) {
    mapsOptions.androidGoogleMapsApiKey = process.env.GOOGLE_MAPS_ANDROID_API_KEY;
  }
  if (process.env.GOOGLE_MAPS_IOS_API_KEY) {
    mapsOptions.iosGoogleMapsApiKey = process.env.GOOGLE_MAPS_IOS_API_KEY;
  }

  return {
    ...config,
    plugins: [
      ...(config.plugins ?? []),
      ['react-native-maps', mapsOptions],
      withReleaseMinificationDisabled,
    ],
  };
};