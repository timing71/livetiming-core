import React from 'react';
import _ from 'lodash';

import { Table } from 'react-bootstrap';

import { format, classNameFromCategory } from '../utils/formats';

function findStateIndex(columnSpec) {
  for (var i=0; i < columnSpec.length; i++) {
    if (columnSpec[i][0] == "State") {
      return i;
    }
  }
  return -1;
}

function findClassIndex(columnSpec) {
  for (var i=0; i < columnSpec.length; i++) {
    if (columnSpec[i][0] == "Class") {
      return i;
    }
  }
  return -1;
}

class TimingRow extends React.Component {
  render() {
    const {position, car, columnSpec} = this.props;
    const cols = [<td key={0} className="timing-row-position">{position}</td>];
    _(columnSpec).forEach((col, index) => {
      const valTuple = car[index];
      let value, flags;
      if (typeof(valTuple) == "object") {
        value = valTuple[0];
        flags = valTuple[1];
      }
      else {
        value = valTuple;
        flags = "";
      }
      cols.push(<td key={index + 1} className={`column_${col[0]} ${flags}`}>{format(value, col[1])}</td>);
    })
    const stateCol = findStateIndex(columnSpec);
    const classCol = findClassIndex(columnSpec);
    const carClass = classNameFromCategory(car[classCol]);
    return (
      <tr className={`car_state_${car[stateCol]} car_class_${carClass}`} >
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
      <Table striped className="timing-table table-condensed">
        <thead>
          <tr className="timing-table-header">
            <td>Pos</td>
            {this.props.columnSpec.map((spec, idx) => <td key={idx}>{spec[0]}</td>)}
          </tr>
        </thead>
        <tbody>
          {carRows}
        </tbody>
      </Table>
    );
  }
}