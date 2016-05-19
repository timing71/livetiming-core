import React from 'react';
import _ from 'lodash';

import { Grid, Row, Col } from 'react-bootstrap';

import Clock from '../components/Clock';
import FlagStatusPanel from '../components/FlagStatusPanel';
import TimingTable from '../components/TimingTable';
import Messages from '../components/Messages';
import TrackData from '../components/TrackData';

class TimingScreen extends React.Component {

  constructor(props) {
    super(props);
    this.state = {
      "cars": [],
      "messages": [],
      "session": {
        "flagState": "green",
        "timeElapsed": 0,
        "timeRemain": 0
      },
      "disconnected": true
    };
    this.handleData = this.handleData.bind(this);
  }

  componentWillMount() {
    const {session} = this.props;

    const service = this.findServiceFromContext(this.props);

    if (service) {
      this.setState({...this.state, service: service});
      this.subscribeToService(service);
    }
  }

  subscribeToService(service) {
    const {session} = this.props;
    if (session && service) {
      session.call("livetiming.service.requestState." + service.uuid).then(
        (result) => {
          this.handleData([result]);
        },
        (error) => {
          console.log("Error");
        }
      );
      session.subscribe(service.uuid, this.handleData).then(
        (sub) => {
          this.subscription = sub;
          session.log("Established subscription to " + service.uuid);
          this.setState({
            ...this.state,
            "disconnected": false
          });
        },
        (error) => {
        }
      );
    }
  }


  componentWillUnmount() {
    this.props.session.unsubscribe(this.subscription);
  }

  findServiceFromContext(context) {
    return _(context.services).find((svc) => svc.uuid === this.props.params.serviceUUID);
  }

  handleData(data) {
    _(data).forEach((message) => {
      if (message.msgClass == 4) {
        this.setState({
          cars: message.payload.cars,
          session: message.payload.session,
          messages: message.payload.messages
        });
      }
    })
  }

  componentWillReceiveProps(nextProps) {
    const service = this.findServiceFromContext(nextProps);
    const disconnected = !service
    if (disconnected != this.state.disconnected) {
      if (disconnected) {
        this.setState({
          ...this.state,
          "messages": [[Date.now() / 1000, "System", "Service no longer available", "system"]].concat(this.state.messages),
          "disconnected": disconnected
        });
      }
      else {
        this.subscribeToService(service);
        this.setState({
          ...this.state,
          service: service,
          "messages": [[Date.now() / 1000, "System", "Service now available", "system"]].concat(this.state.messages),
          "disconnected": disconnected
        });
      }
    }
  }
  
  render() {
    if (!this.state.service) {
      return <p>Service not found</p>;
    }
    let remaining;
    if (this.state.session.lapsRemain !== undefined) {
      remaining = <div className="clock">{this.state.session.lapsRemain} lap{this.state.session.lapsRemain == 1 ? "" : "s"} remaining</div>
    }
    else {
      remaining = <Clock seconds={this.state.session.timeRemain} countdown={true} caption="remaining" />
    }
    return (
      <Grid fluid={true} className="screen timing-screen">
        <Row>
          <Col md={2}>
            <Clock seconds={this.state.session.timeElapsed} caption="elapsed" />
          </Col>
          <Col md={8}>
            <FlagStatusPanel flag={this.state.session.flagState} text={this.state.service.name} />
          </Col>
          <Col md={2}>
            {remaining}
          </Col>
        </Row>
        <Row className="timing-table-container">
          <Col md={12} className="full-height">
            <TimingTable columnSpec={this.state.service.colSpec} cars={this.state.cars} />
          </Col>
        </Row>
        <Row className="messages-container">
          <Col md={8} className="full-height">
            <Messages messages={this.state.messages} />
          </Col>
          <Col md={4}>
            <TrackData spec={this.state.service.trackDataSpec} dataset={this.state.session.trackData} />
          </Col>
        </Row>
      </Grid>
    );
  }
}

export default TimingScreen;
