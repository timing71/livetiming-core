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

  componentWillReceiveProps() {
    this.setState({...this.state, refTime: Date.now()})
  }

  updateTimer() {
    if (this.props.seconds != null) {
      const delta = Math.ceil((Date.now() - this.state.refTime) / 1000);
      if (this.props.countdown) {
        this.setState({...this.state, seconds : Math.max(this.props.seconds - delta, 0)});
      }
      else {
        this.setState({...this.state, seconds : this.props.seconds + delta});
      }
    }
  }
  render() {
    return <div className="clock">{timeWithHours(this.state.seconds)} {this.props.caption}</div>;
  }
}