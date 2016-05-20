import React from 'react';
import ReactDOM from 'react-dom';
import ga from 'react-ga';
import { Router, browserHistory } from 'react-router';
import routes from './routes';

ga.initialize('UA-78071221-1');

function logPageView() {
  ga.pageview(window.location.pathname);
}

ReactDOM.render(
  <Router history={browserHistory} onUpdate={logPageView}>{routes}</Router>,
  document.getElementById('app')
);
