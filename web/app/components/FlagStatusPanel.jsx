import React from 'react';

export default class FlagStatusPanel extends React.Component {
  render() {
    const {flag, text} = this.props;
    return <div className={"flag-status flag-status-" + flag}>{text}</div>
  }
}