import React from 'react';

import {timeWithHours} from '../utils/formats';

export default class Clock extends React.Component {
  constructor(props) {
    super(props);
    this.updateTimer = this.updateTimer.bind(this);
    this.state = { seconds: 0, refTime: Date.now() };
    this.interval = null;
  }

  componentDidMount() {
    this.updateTimer();
    if (this.interval === null) {
      this.interval = setInterval(this.updateTimer, 1000);
    }
  }

  componentWillUnmount() {
    if (this.interval !== null) {
      clearInterval(this.interval);
    }
  }

  componentWillReceiveProps(newProps) {
    if (newProps.seconds != this.props.seconds) {
      this.setState({refTime: Date.now()});
    }
    else if (newProps.pause == false && this.props.pause === true) {
      this.setState({refTime: Date.now() - (1000 * this.state.delta)});
    }
  }

  updateTimer() {
    if (this.props.seconds != null) {
      const delta = this.props.pause ? this.state.delta : Math.ceil((Date.now() - this.state.refTime) / 1000);
      if (this.props.countdown) {
        this.setState({seconds: Math.max(this.props.seconds - delta, 0), delta: delta});
      }
      else {
        this.setState({seconds: this.props.seconds + delta, delta: delta});
      }
    }
  }
  render() {
    return <div className="clock">{timeWithHours(this.state.seconds)} {this.props.caption}</div>;
  }
}