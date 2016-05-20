import React from 'react';

const packageJson = require('../../package.json');

export default class Version extends React.Component {
  render() {
    return <p>Version: {packageJson.version}</p>;
  }
}