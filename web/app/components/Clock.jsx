import React from 'react';

import {timeWithHours} from '../utils/formats';

export default class Clock extends React.Component {
  render() {
    return <div className="clock">{timeWithHours(this.props.seconds)} {this.props.caption}</div>;
  }
}