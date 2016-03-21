import React from 'react';

export default class Messages extends React.Component {
  render() {
    const { messages } = this.props;
    return <p>{messages}</p>;
  }
}