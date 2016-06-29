import React from 'react';
import { browserHistory } from 'react-router';

import { Glyphicon, Nav, NavDropdown, NavItem, MenuItem} from 'react-bootstrap';
import ReactSlider from 'react-slider';

import TimingScreen from '../screens/TimingScreen';
import {ServiceNotAvailable} from '../components/Modals';

export default class RecordingProvider extends React.Component {

  constructor(props) {
    super(props);
    this.state = {
      time: 0,
      playing: false,
      lastFrame: 0,
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
    console.log(`Time now ${time}`);
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

  play() {
    const playInterval = setInterval(() => {this.tick()}, 1000);
    this.setState({playing: true, playInterval: playInterval, lastFrame: Date.now() - this.state.lastFrame});
  }

  pause() {
    clearInterval(this.state.playInterval);
    this.setState({playing: false, playInterval: undefined, lastFrame: Date.now() - this.state.lastFrame});

  }

  tick() {
    const timingUpdateInterval = 10;
    const now = Date.now();
    if (now >= this.state.lastFrame + (timingUpdateInterval * 1000)) {
      this.setTime(this.state.time + timingUpdateInterval);
      this.setState({lastFrame: now});
    }
  }

  render() {
    const service = this.getServiceFromProps();
    if (!service) {
      return <ServiceNotAvailable />;
    }
    const {session, cars, messages} = this.state.recordedState;
    const serviceTime = Math.ceil(service["startTime"]) + this.state.time;
    const menu = (
      <PlaybackControls
        position={this.state.time}
        length={service.duration}
        playing={this.state.playing}
        onPlay={this.play.bind(this)}
        onPause={this.pause.bind(this)}
        onSeek={this.setTime.bind(this)}
      />
    );
    return <TimingScreen
      service={service}
      session={session}
      cars={cars}
      messages={messages}
      menu={menu}
      pauseClocks={!this.state.playing}
      serviceTime={serviceTime}
    />;
  }
}

const PlaybackControls = ({position, length, playing, onPlay, onPause, onSeek}) => (
  <Nav className="timing-menu">
    <NavItem eventKey="playPause" onClick={() => playing ? onPause() : onPlay()}>
      <Glyphicon glyph={playing ? "pause" : "play"} />
    </NavItem>
    <NavDropdown eventKey={1} title={<Glyphicon glyph="cog" />} id="nav-dropdown">
      <MenuItem header>
        <span>Position</span>
        <ReactSlider max={length} value={position} onChange={onSeek} withBars />
      </MenuItem>
      <MenuItem divider />
      <MenuItem eventKey="1.2" onClick={() => browserHistory.push("/")}>Main menu</MenuItem>
    </NavDropdown>
  </Nav>
);