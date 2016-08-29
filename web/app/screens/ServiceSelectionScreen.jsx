import React from 'react';

import {Grid, Row, Col, PageHeader, Panel} from 'react-bootstrap';

import ServiceList from '../components/ServiceList';
import Version from '../components/Version';

class ServiceSelectionScreen extends React.Component {
  render() {
    return (
      <Grid>
        <Row>
          <Col md={12}>
            <PageHeader>Live Timing Aggregator</PageHeader>
          </Col>
        </Row>
        <Row>
          <Col md={6} sm={12}>
            <Panel header="Live now">
              <ServiceList services={this.props.services} linkPart="timing" header="Available Timing Services"/>
            </Panel>
          </Col>
          <Col md={6} sm={12}>
            <Panel header="Replays">
              <ServiceList services={this.props.recordings} linkPart="recording" header="Available Recordings"/>
            </Panel>
          </Col>
        </Row>
        <Row>
          <Col md={4} mdOffset={8}>
            <Version />
            <p>Copyright &copy; James Muscat 2016. Feed data remains owner of original data source.</p>
          </Col>
        </Row>
      </Grid>
    );
  }
}

export default ServiceSelectionScreen;
