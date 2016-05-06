import React from 'react';
import _ from 'lodash';

import { Grid, Row, Col } from 'react-bootstrap';

import Clock from '../components/Clock';
import FlagStatusPanel from '../components/FlagStatusPanel';
import TimingTable from '../components/TimingTable';
import Messages from '../components/Messages';

export default class TimingScreen extends React.Component {

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
    const {session, service} = this.props;

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
          session: message.payload.session
        });
      }
    })
  }
  
  render() {
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
            <Clock seconds={this.state.session.timeRemain} caption="remaining" />
          </Col>
        </Row>
        <Row className="timing-table-container">
          <Col md={12} className="full-height">
            <TimingTable columnSpec={this.props.service.colSpec} cars={this.state.cars} />
          </Col>
        </Row>
        <Row>
          <Col md={8}>
            <Messages messages={this.state.messages} />
          </Col>
          <Col md={4}>
            <p>Track Data</p>
          </Col>
        </Row>
      </Grid>
    );
  }
}