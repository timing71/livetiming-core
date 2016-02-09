import React from 'react';
import autobahn from '../lib/autobahn';
import _ from 'lodash';

import ServiceList from './ServiceList';

export default class App extends React.Component {

  constructor(props) {
    super(props);
    this.state = {
      "services": {},
      "chosenService": null
    };
    this.setChosenService = this.setChosenService.bind(this);
  }

  componentWillMount() {
    console.log("Ok, Autobahn loaded", autobahn.version);
    const connection = new autobahn.Connection({
      url: "ws://127.0.0.1:5080/ws",
      realm: "timing"
    });
    connection.onopen = (session, details) => {
      session.call("livetiming.directory.listServices").then((result) => {
        this.setState(
          ...this.state,
          {"services": result}
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
      return <ServiceList services={this.state.services} onChooseService={this.setChosenService} />
    }
    const service = _(this.state.services).find((svc) => svc.uuid === this.state.chosenService);
    return <p>{service.description}</p>;
  }

}