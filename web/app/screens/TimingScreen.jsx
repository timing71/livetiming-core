import React from 'react';

import { Grid, Row, Col } from 'react-bootstrap';

import TimingTable from '../components/TimingTable';

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
  }

  componentWillMount() {
    const {session, service} = this.props;
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
    console.log(data);
  }
  
  render() {
    return (
      <Grid fluid={true} className="screen timing-screen">
        <Row>
          <Col md={2}>
            <p>{this.state.session.timeElapsed}</p>
          </Col>
          <Col md={8}>
            <p>{this.props.service.description}</p>
          </Col>
          <Col md={2}>
            <p>{this.state.session.timeRemain}</p>
          </Col>
        </Row>
        <Row className="timing-table-container">
          <Col md={12} className="full-height">
            <TimingTable cars={this.state.cars} />
          </Col>
        </Row>
        <Row>
          <Col md={8}>
            <p>Messages</p>
          </Col>
          <Col md={4}>
            <p>Track Data</p>
          </Col>
        </Row>
      </Grid>
    );
  }
}