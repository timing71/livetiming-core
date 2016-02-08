import React from 'react';
import autobahn from '../lib/autobahn';

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
      });
    };
    connection.open();
  }

  render() {
    return <p>Hello, World!</p>;
  }

}