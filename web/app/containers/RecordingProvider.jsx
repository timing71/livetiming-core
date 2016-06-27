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
    // Get service from new props, not existing ones - in case it hasn't made it that far yet
    const service = _(newProps.recordings).find((svc) => svc.uuid === this.props.params.recordingUUID);

    if (service && newProps.session) {
      this.setTime(0, service);
    }
  }

  componentWillMount() {
    if (this.props.session) {
      this.setTime(0, this.getServiceFromProps());
    }
  }

  getServiceFromProps() {
    return _.find(this.props.recordings, (svc) => svc.uuid === this.props.params.recordingUUID);
  }

  setTime(time, useService) {
    const service = useService || this.getServiceFromProps();
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
    const service = this.getServiceFromProps();
    if (!service) {
      return <ServiceNotAvailable />;
    }
    const {session, cars, messages} = this.state.recordedState;
    return <TimingScreen service={service} session={session} cars={cars} messages={messages} menu={<PlaybackControls />} />
  }
}

const PlaybackControls = () => (
  <Nav pullRight={true}>
    <NavDropdown eventKey={1} title={<Glyphicon glyph="cog" />} id="nav-dropdown">
      <MenuItem eventKey="1.2" onClick={() => browserHistory.push("/")}>Main menu</MenuItem>
    </NavDropdown>
  </Nav>
);