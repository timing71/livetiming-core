import React from 'react';

import { Grid, Row, Col } from 'react-bootstrap';

import Clock from '../components/Clock';
import FlagStatusPanel from '../components/FlagStatusPanel';
import TimingTable from '../components/TimingTable';
import Messages from '../components/Messages';
import TrackData from '../components/TrackData';


class TimingScreen extends React.Component {

  render() {
    const {session, service, cars, messages, menu} = this.props;
    let remaining;
    if (session.lapsRemain !== undefined) {
      remaining = <div className="clock">{session.lapsRemain} lap{session.lapsRemain == 1 ? "" : "s"} remaining</div>
    }
    else {
      remaining = <Clock seconds={session.timeRemain} countdown={true} caption="remaining" />
    }
    return (
      <Grid fluid={true} className="screen timing-screen">
        <Row className="timing-screen-header">
          <Col sm={2}>
            <Clock seconds={session.timeElapsed} caption="elapsed" />
          </Col>
          <Col sm={7}>
            <FlagStatusPanel flag={session.flagState} text={service.name} />
          </Col>
          <Col sm={2}>
            {remaining}
          </Col>
          <Col sm={1}>
            {menu}
          </Col>
        </Row>
        <Row className="timing-table-container">
          <Col md={12} className="full-height">
            <TimingTable columnSpec={service.colSpec} cars={cars} />
          </Col>
        </Row>
        <Row className="messages-container">
          <Col md={8} className="full-height">
            <Messages messages={messages} />
          </Col>
          <Col md={4}>
            <TrackData spec={service.trackDataSpec} dataset={session.trackData} />
          </Col>
        </Row>
      </Grid>
    );
  }
}

export default TimingScreen;
