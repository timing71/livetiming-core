import React from 'react';

const packageJson = require('../../package.json');

const Version = () => (<p>Version: {packageJson.version}</p>);

export default Version;
