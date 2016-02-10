import React from 'react';

import ServiceList from '../components/ServiceList';

export default class ServiceSelectionScreen extends React.Component {
  render() {
    return <ServiceList services={this.props.services} onChooseService={this.props.onChooseService} />
  }
}