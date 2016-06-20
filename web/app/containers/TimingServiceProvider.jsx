import React from 'react';
import { Glyphicon, Nav, NavDropdown, MenuItem} from 'react-bootstrap';
import _ from 'lodash';

import { browserHistory } from 'react-router';

import TimingScreen from '../screens/TimingScreen';
import Spinner from '../components/Spinner';
import {ServiceNotAvailable} from '../components/Modals';

export default class TimingServiceProvider extends React.Component {

  constructor(props) {
    super(props);
    this.state = {
      "cars": [],
      "messages": [],
      "session": {
        "flagState": "none",
        "timeElapsed": 0,
        "timeRemain": 0
      },
      "disconnected": true,
      "delay": 0
    };
    this.handleData = this.handleData.bind(this);
    this.messageQueue = []
  }

  componentWillMount() {
    const service = this.findServiceFromContext(this.props);

    if (service) {
      this.setState({...this.state, service: service});
      this.subscribeToService(service);
    }
  }

  subscribeToService(service) {
    const {session} = this.props;
    if (session && service) {
      session.call("livetiming.service.requestState." + service.uuid).then(
        (result) => {
          this.handleData([result]);
        },
        (error) => {
          console.log("Error:", error);
        }
      );
      session.subscribe(service.uuid, this.handleData).then(
        (sub) => {
          this.subscription = sub;
          session.log("Established subscription to " + service.uuid);
          this.setState({
            ...this.state,
            "disconnected": false
          });
        },
        (error) => {
        }
      );
    }
  }


  componentWillUnmount() {
    if (this.subscription) {
      this.props.session.unsubscribe(this.subscription);
    }
    if (this.delayedMessagesInterval) {
      clearInterval(this.delayedMessagesInterval);
    }
  }

  findServiceFromContext(context) {
    return _(context.services).find((svc) => svc.uuid === this.props.params.serviceUUID);
  }

  handleData(data) {
    _(data).forEach((message) => {
      if (message.msgClass == 4) {
        this.delayMessage(message.payload);
      }
    })
  }

  delayMessage(payload) {
    if (this.state.delay == 0) {
      this.applyMessage(payload);
    }
    else {
      const arrivedAt = Date.now();
      this.messageQueue.push([arrivedAt, payload]);
    }
  }

  applyMessage(payload) {
    this.setState({
      cars: payload.cars,
      session: payload.session,
      messages: payload.messages
    });
  }

  setDelay(delay) {
    this.setState(
      {
        ...this.state,
        delay: delay
      }
    );
    if (delay > 0) {
      this.delayedMessagesInterval = setInterval(this.processMessageQueue.bind(this), 1000);
    }
    else if (delay == 0) {
      clearInterval(this.delayedMessagesInterval);
      // Flush the queue - calling processMessageQueue() would use old state
      while(this.messageQueue.length > 0) {
        const msg = this.messageQueue.shift();
        this.applyMessage(msg[1]);
      }
    }
  }

  processMessageQueue() {
    while(this.messageQueue.length > 0 && (this.messageQueue[0][0] + (1000 * this.state.delay)) < Date.now()) {
      const msg = this.messageQueue.shift();
      this.applyMessage(msg[1]);
    }
  }

  componentWillReceiveProps(nextProps) {
    const service = this.findServiceFromContext(nextProps);
    const disconnected = !service;
    if (disconnected != this.state.disconnected) {
      if (disconnected) {
        this.setState({
          ...this.state,
          "messages": [[Date.now() / 1000, "System", "Service no longer available", "system"]].concat(this.state.messages),
          "disconnected": disconnected
        });
      }
      else {
        this.subscribeToService(service);
        this.setState({
          ...this.state,
          service: service,
          "messages": [[Date.now() / 1000, "System", "Service now available", "system"]].concat(this.state.messages),
          "disconnected": disconnected
        });
      }
    }
  }
  
  

  render() {
    if (!this.state.service) {
      return <ServiceNotAvailable />;
    }

    const {delay, service, session, cars, messages} = this.state;

    const menu = (
      <Nav pullRight={true}>
        <NavDropdown eventKey={1} title={<Glyphicon glyph="cog" />} id="nav-dropdown">
          <MenuItem header><span>Delay: <Spinner value={delay} onChange={this.setDelay.bind(this)} constrain={(v) => Math.max(v, 0)} /></span></MenuItem>
          <MenuItem divider />
          <MenuItem eventKey="1.2" onClick={() => browserHistory.push("/")}>Main menu</MenuItem>
        </NavDropdown>
      </Nav>
    );

    return <TimingScreen service={service} session={session} cars={cars} messages={messages} menu={menu} />
  }
  
}