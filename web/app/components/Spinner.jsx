import React from 'react';

import {Button, FormControl, InputGroup} from 'react-bootstrap';

export default class Spinner extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      value: props.value || 0
    }
  }

  increment() {
    this.onChange(this.state.value + 1);

  }

  decrement() {
    this.onChange(this.state.value - 1);
  }

  constrain(val) {
    if (this.props.constrain) {
      return this.props.constrain(val);
    }
    return val;
  }

  onChange(newValue) {
    const constrainedValue = this.constrain(newValue);
    this.setState({value: constrainedValue});
    if (this.props.onChange) {
      this.props.onChange(constrainedValue);
    }
  }

  render() {
    return (
      <InputGroup>
        <InputGroup.Button>
          <Button onClick={this.decrement.bind(this)}>-</Button>
        </InputGroup.Button>
        <FormControl type="text" value={this.state.value} onChange={(e) => this.onChange(parseInt(e.target.value, 10))} ref="spinner" />
        <InputGroup.Button>
          <Button onClick={this.increment.bind(this)}>+</Button>
        </InputGroup.Button>
      </InputGroup>
    );
  }
}