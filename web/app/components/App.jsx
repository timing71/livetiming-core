import React from 'react';
import autobahn from '../lib/autobahn';
import _ from 'lodash';

import { ROUTER_URL } from '../config/settings';

import ServiceSelectionScreen from '../screens/ServiceSelectionScreen';
import TimingScreen from '../screens/TimingScreen';

class App extends React.Component {

  constructor(props) {
    super(props);
    this.state = {
      "services": [],
      "session": null
    };
  }

  getChildContext() {
    return {
      services: this.state.services,
      session: this.state.session
    }
  }

  componentWillMount() {
    console.log("Ok, Autobahn loaded", autobahn.version);
    const connection = new autobahn.Connection({
      url: ROUTER_URL,
      realm: "timing"
    });
    connection.onopen = (session, details) => {
      this.setState({...this.state, "session": session});
      session.call("livetiming.directory.listServices").then((result) => {
        this.setState({
          ...this.state,
          "services": result}
        );
      });
    };
    connection.open();
  }

  render() {
    return this.props.children;
  }

}

App.childContextTypes = {
  session: React.PropTypes.object,
  services: React.PropTypes.array
};

export default App;