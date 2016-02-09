import React from 'react';


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
        <div>
          <h3>Available Timing Services</h3>
          <ul>
            {services.map((svc) => <ServiceListEntry key={svc.uuid} service={svc} onChooseService={() => onChooseService(svc.uuid)} />)}
          </ul>
        </div>
        );
  }
}