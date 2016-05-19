import React, {Children, cloneElement} from 'react';
import autobahn from '../lib/autobahn';
import _ from 'lodash';

import { ROUTER_URL } from '../config/settings';

class App extends React.Component {

  constructor(props) {
    super(props);
    this.state = {
      "services": [],
      "session": null
    };
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

      session.subscribe("livetiming.control", this.handleControlMessage.bind(this)).then(
          (sub) => {
            this.subscription = sub;
            session.log ("Established subscription to control channel");
          },
          (error) => {}
        );
    };
    connection.open();
  }

  componentWillUnmount() {
    this.state.session.unsubscribe(this.subscription);
  }
  
  handleControlMessage(data) {
    _(data).forEach((message) => {
      console.log(message);
      if (message.msgClass == 5) {
        this.setState({
          ...this.state,
          "services": message.payload
        });
      }
    })
  }

  render() {
    if (!this.state.session) {
      return <p>loading</p>;
    }
    const {children} = this.props;
    const newProps = {
      session: this.state.session,
      services: this.state.services
    };
    const childrenWithProps = Children.map(
      children,
      (child) => cloneElement(children, newProps)
    );
    return <div className="full-height">{childrenWithProps}</div>;
  }

}

export default App;