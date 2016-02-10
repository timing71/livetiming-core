import React from 'react';

import { Grid, Row, Col } from 'react-bootstrap';

export default class TimingScreen extends React.Component {
  render() {
    return (
      <Grid fluid={true} className="timingScreen">
        <Row>
          <Col md={3}>
            <p>00:00:00</p>
          </Col>
          <Col md={6}>
            <p>{this.props.service.description}</p>
          </Col>
          <Col md={3}>
            <p>00:00:00</p>
          </Col>
        </Row>
        <Row>
          <Col md={12}>
            <p>Timing Table</p>
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