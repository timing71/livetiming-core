import React from 'react';

import {Modal, ModalBody} from 'react-bootstrap';

export default class Loading extends React.Component {
  render() {
    return (
      <Modal show={true} animation={false} className="loading">
        <ModalBody className="full-height">
          Loading...
        </ModalBody>
      </Modal>
    );
  }
}