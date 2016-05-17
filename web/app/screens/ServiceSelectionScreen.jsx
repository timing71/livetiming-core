import React from 'react';

import { Grid, Row, Col, PageHeader } from 'react-bootstrap';

import ServiceList from '../components/ServiceList';

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
          <Col md={12}>
            <ServiceList services={this.context.services} />
          </Col>
        </Row>
        <Row>
          <Col md={4} mdOffset={8}>
            <p>Copyright &copy; James Muscat 2016. Feed data remains owner of original data source.</p>
          </Col>
        </Row>
      </Grid>
    );
  }
}

ServiceSelectionScreen.contextTypes = {
  services: React.PropTypes.array
};

export default ServiceSelectionScreen;