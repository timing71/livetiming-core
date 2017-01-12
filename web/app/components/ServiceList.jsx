import React from 'react';
import { Link } from 'react-router';

const ServiceListEntry = ({linkPart, service}) => (<li><Link to={`/${linkPart}/${service.uuid}`}>{service.name} - {service.description}</Link></li>);

const ServiceList = ({services, onChooseService, linkPart}) => {
  if (!services.length) {
    return <p>No services available.</p>;
  }
  return (
    <ul>
      {services.map((svc) => <ServiceListEntry key={svc.uuid} service={svc} onChooseService={() => onChooseService(svc.uuid)} linkPart={linkPart} />)}
    </ul>
  );
};

export default ServiceList;
