import React from 'react';
import {Link} from 'react-router';
import {Modal, ModalBody} from 'react-bootstrap';

export class TimingModal extends React.Component {
  render() {
    return (
      <Modal show={true} animation={false} className="timing-modal">
        <ModalBody className="full-height">
          {this.props.children}
        </ModalBody>
      </Modal>
    );
  }
}

export class Loading extends React.Component {
  render() {
    return (
      <TimingModal>
        Loading...
      </TimingModal>
    );
  }
}

export class ServiceNotAvailable extends React.Component {
  render() {
    return (
      <TimingModal>
        <p>Service not available.</p>
        <Link to="/">Back to main menu</Link>
      </TimingModal>
    );
  }
}