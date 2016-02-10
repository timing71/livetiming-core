import React from 'react';

import { Table } from 'react-bootstrap';

export default class TimingTable extends React.Component {
  render() {
    return (
      <Table striped className="full-height">
        <thead>
          <tr className="timing-table-header">
            <td>Pos</td>
            <td>Num</td>
            <td>State</td>
            <td>Cat</td>
            <td>Team</td>
            <td>Driver</td>
            <td>Car</td>
            <td>T</td>
            <td>Laps</td>
            <td>Gap</td>
            <td>Int</td>
            <td>Last</td>
            <td>Best</td>
            <td>Spd</td>
            <td>Pits</td>
          </tr>
        </thead>
      </Table>
    );
  }
}