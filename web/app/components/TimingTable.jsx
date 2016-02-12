import React from 'react';

import { Table } from 'react-bootstrap';

export default class TimingTable extends React.Component {
  render() {
    return (
      <Table striped className="full-height">
        <thead>
          <tr className="timing-table-header">
            <td>Pos</td>
            {this.props.columnSpec.map(spec => <td>{spec[0]}</td>)}
          </tr>
        </thead>
      </Table>
    );
  }
}