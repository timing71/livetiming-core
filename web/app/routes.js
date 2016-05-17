import React from 'react';
import { IndexRoute, Route } from 'react-router';

import App from './components/App.jsx';
import ServiceSelectionScreen from './screens/ServiceSelectionScreen';
import TimingScreen from './screens/TimingScreen';

const routes = <Route path="/" component={App}>
  <IndexRoute component={ServiceSelectionScreen} />
  <Route path="timing/:serviceUUID" component={TimingScreen} />
</Route>;

export default routes;