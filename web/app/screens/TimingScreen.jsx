import React from 'react';
import _ from 'lodash';

import { Grid, Row, Col } from 'react-bootstrap';

import Clock from '../components/Clock';
import FlagStatusPanel from '../components/FlagStatusPanel';
import TimingTable from '../components/TimingTable';
import Messages from '../components/Messages';
import TrackData from '../components/TrackData';

class TimingScreen extends React.Component {

  constructor(props) {
    super(props);
    this.state = {
      "cars": [],
      "messages": [],
      "session": {
        "flagState": "green",
        "timeElapsed": 0,
        "timeRemain": 0
      }
    };
    this.handleData = this.handleData.bind(this);
  }

  componentWillMount() {
    const {service} = this.props;
    const {session} = this.context;

    session.call("livetiming.service.requestState." + service.uuid).then((result) => {
      this.handleData([result]);
      });

    session.subscribe(service.uuid, this.handleData).then(
      (sub) => {
        this.subscription = sub;
        session.log ("Established subscription to " + service.uuid);
      },
      (error) => {}
    );
  }

  componentWillUnmount() {
    const {session, service} = this.props;
    session.unsubscribe(service.uuid);
  }
  
  handleData(data) {
    _(data).forEach((message) => {
      if (message.msgClass == 4) {
        this.setState({
          cars: message.payload.cars,
          session: message.payload.session,
          messages: message.payload.messages
        });
      }
    })
  }
  
  render() {
    let remaining;
    if (this.state.session.lapsRemain !== undefined) {
      remaining = <div className="clock">{this.state.session.lapsRemain} lap{this.state.session.lapsRemain == 1 ? "" : "s"} remaining</div>
    }
    else {
      remaining = <Clock seconds={this.state.session.timeRemain} countdown={true} caption="remaining" />
    }
    return (
      <Grid fluid={true} className="screen timing-screen">
        <Row>
          <Col md={2}>
            <Clock seconds={this.state.session.timeElapsed} caption="elapsed" />
          </Col>
          <Col md={8}>
            <FlagStatusPanel flag={this.state.session.flagState} text={this.props.service.name} />
          </Col>
          <Col md={2}>
            {remaining}
          </Col>
        </Row>
        <Row className="timing-table-container">
          <Col md={12} className="full-height">
            <TimingTable columnSpec={this.props.service.colSpec} cars={this.state.cars} />
          </Col>
        </Row>
        <Row className="messages-container">
          <Col md={8} className="full-height">
            <Messages messages={this.state.messages} />
          </Col>
          <Col md={4}>
            <TrackData spec={this.props.service.trackDataSpec} dataset={this.state.session.trackData} />
          </Col>
        </Row>
      </Grid>
    );
  }
}

TimingScreen.contextTypes = {
  session: React.PropTypes.object
};

export default TimingScreen;