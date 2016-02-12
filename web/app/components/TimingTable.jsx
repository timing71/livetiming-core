import React from 'react';
import _ from 'lodash';

import { Table } from 'react-bootstrap';

import { format } from '../utils/formats';

class TimingRow extends React.Component {
  render() {
    const {position, car, columnSpec} = this.props;
    const cols = [<td key={0}>{position}</td>];
    _(columnSpec).forEach((col, index) => {
      cols.push(<td key={index + 1}>{format(car[index], col[1])}</td>);
    })
    return (
      <tr>
        {cols}
      </tr>
    );
  }
}

export default class TimingTable extends React.Component {
  render() {
    const carRows = [];
    _(this.props.cars).forEach((car, position) => {
      carRows.push(<TimingRow car={car} key={position} position={position + 1} columnSpec={this.props.columnSpec} />);
    });
    return (
      <Table striped className="timing-table">
        <thead>
          <tr className="timing-table-header">
            <td>Pos</td>
            {this.props.columnSpec.map(spec => <td>{spec[0]}</td>)}
          </tr>
        </thead>
        <tbody>
          {carRows}
        </tbody>
      </Table>
    );
  }
}