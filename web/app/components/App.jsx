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
      "chosenService": null,
      "session": null
    };
    this.setChosenService = this.setChosenService.bind(this);
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

  setChosenService(serviceUUID) {
    this.setState({
      ...this.state,
      "chosenService": serviceUUID
    });
  }

  render() {
    if (this.state.chosenService == null) {
      return <ServiceSelectionScreen onChooseService={this.setChosenService} />
    }
    const service = _(this.state.services).find((svc) => svc.uuid === this.state.chosenService);
    return <TimingScreen service={service} />;
  }

}

App.childContextTypes = {
  session: React.PropTypes.object,
  services: React.PropTypes.array
};

export default App;