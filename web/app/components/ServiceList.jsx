import React from 'react';
import { Link } from 'react-router';
import { Panel } from 'react-bootstrap';

class ServiceListEntry extends React.Component {
  render() {
    const {linkPart, service} = this.props;
    return <li><Link to={`/${linkPart}/${service.uuid}`}>{service.description}</Link></li>
  }
}

export default class ServiceList extends React.Component {
  render() {
    const {services, onChooseService, header, linkPart} = this.props;
    if (!services.length) {
      return <p>No services available.</p>;
    }
    return (
        <Panel header={header}>
          <ul>
            {services.map((svc) => <ServiceListEntry key={svc.uuid} service={svc} onChooseService={() => onChooseService(svc.uuid)} linkPart={linkPart} />)}
          </ul>
        </Panel>
        );
  }
}