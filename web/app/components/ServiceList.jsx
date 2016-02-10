import React from 'react';

import { Panel } from 'react-bootstrap';

class ServiceListEntry extends React.Component {
  render() {
    const {service, onChooseService} = this.props;
    return <li onClick={onChooseService}>{service.description}</li>
  }
}

export default class ServiceList extends React.Component {
  render() {
    const {services, onChooseService} = this.props;
    if (!services.length) {
      return <p>No services available.</p>;
    }
    return (
        <Panel header="Available Timing Services">
          <ul>
            {services.map((svc) => <ServiceListEntry key={svc.uuid} service={svc} onChooseService={() => onChooseService(svc.uuid)} />)}
          </ul>
        </Panel>
        );
  }
}