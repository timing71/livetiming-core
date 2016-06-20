import React from 'react';
import { IndexRoute, Route } from 'react-router';

import App from './components/App.jsx';
import TimingServiceProvider from './containers/TimingServiceProvider';
import ServiceSelectionScreen from './screens/ServiceSelectionScreen';

const routes = <Route path="/" component={App}>
  <IndexRoute component={ServiceSelectionScreen} />
  <Route path="timing/:serviceUUID" component={TimingServiceProvider} />
</Route>;

export default routes;