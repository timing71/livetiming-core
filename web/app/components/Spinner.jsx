import React from 'react';
import $ from 'jquery';

import {Button, FormControl, FormGroup, InputGroup} from 'react-bootstrap';

export default class Spinner extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      value: props.value || 0
    }
  }

  increment() {
    const constrain = this.props.constrain || ((a) => a);
    const newValue = constrain(this.state.value + 1);
    this.setState({value: newValue});
    if (this.props.onChange) {
      this.props.onChange(newValue);
    }
  }

  decrement() {
    const constrain = this.props.constrain || ((a) => a);
    const newValue = constrain(this.state.value - 1);
    this.setState({value: newValue});
    if (this.props.onChange) {
      this.props.onChange(newValue);
    }
  }

  render() {
    return (
      <InputGroup>
        <InputGroup.Button>
          <Button onClick={this.decrement.bind(this)}>-</Button>
        </InputGroup.Button>
        <FormControl type="text" value={this.state.value} ref="spinner" />
        <InputGroup.Button>
          <Button onClick={this.increment.bind(this)}>+</Button>
        </InputGroup.Button>
      </InputGroup>
    );
  }
}