import React from 'react';
import { browserHistory } from 'react-router';

import { Glyphicon, Nav, NavDropdown, MenuItem} from 'react-bootstrap';

import TimingScreen from '../screens/TimingScreen';
import {ServiceNotAvailable} from '../components/Modals';

export default class RecordingProvider extends React.Component {

  constructor(props) {
    super(props);
    this.state = {
      time: 0,
      recordedState: {
        "cars": [],
        "messages": [],
        "session": {
          "flagState": "none",
          "timeElapsed": 0,
          "timeRemain": 0
        }
      }
    }
  }

  componentWillReceiveProps(newProps) {
    const service = _(newProps.recordings).find((svc) => svc.uuid === this.props.params.recordingUUID);

    if (service) {
      this.setState({...this.state, service: service});
      if (this.props.session) {
        this.setTime(0, service);
      }
    }
  }

  setTime(time, useService) {
    const service = useService || this.state.service;
    if (!service) {
      console.log("setTime called without a service");
      return;
    }
    this.props.session.call(`livetiming.service.requestState.${service.uuid}`, [time]).then(
      (result) => {
        this.setState({
          ...this.state,
          time: time,
          recordedState: result
        });
      },
      (error) => {
        console.log("Error:", error);
      }
    );
  }

  render() {
    if (!this.state.service) {
      return <ServiceNotAvailable />;
    }
    const {session, cars, messages} = this.state.recordedState;
    return <TimingScreen service={this.state.service} session={session} cars={cars} messages={messages} menu={<PlaybackControls />} />
  }
}

const PlaybackControls = () => (
  <Nav pullRight={true}>
    <NavDropdown eventKey={1} title={<Glyphicon glyph="cog" />} id="nav-dropdown">
      <MenuItem eventKey="1.2" onClick={() => browserHistory.push("/")}>Main menu</MenuItem>
    </NavDropdown>
  </Nav>
);