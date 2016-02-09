import React from 'react';
import autobahn from '../lib/autobahn';

import ServiceList from './ServiceList';

export default class App extends React.Component {

  constructor(props) {
    super(props);
    this.state = {"services": []};
  }

  componentWillMount() {
    console.log("Ok, Autobahn loaded", autobahn.version);
    const connection = new autobahn.Connection({
      url: "ws://127.0.0.1:5080/ws",
      realm: "timing"
    });
    connection.onopen = (session, details) => {
      session.call("livetiming.directory.listServices").then((result) => {
        this.setState({"services": result});
        console.log(result);
      });
    };
    connection.open();
  }

  render() {
    return <ServiceList services={this.state.services} />;
  }

}