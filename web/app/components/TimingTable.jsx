import React from 'react';

import _ from 'lodash';

import { OverlayTrigger, Table, Tooltip } from 'react-bootstrap';

import { format, classNameFromCategory } from '../utils/formats';

function findStateIndex(columnSpec) {
  for (let i=0; i < columnSpec.length; i++) {
    if (columnSpec[i][0] == "State") {
      return i;
    }
  }
  return -1;
}

function findClassIndex(columnSpec) {
  for (let i=0; i < columnSpec.length; i++) {
    if (columnSpec[i][0] == "Class") {
      return i;
    }
  }
  return -1;
}

function findRaceNumberIndex(columnSpec) {
  for (let i=0; i < columnSpec.length; i++) {
    if (columnSpec[i][0] == "Num") {
      return i;
    }
  }
  return -1;
}

const TimingRow = ({position, car, columnSpec}) => {
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
  });

  const hasSetSB = _(car).find((c) => (typeof(c) == "object" && c[1] == "sb-new"));
  const stateCol = findStateIndex(columnSpec);
  const classCol = findClassIndex(columnSpec);
  const carClass = classNameFromCategory(car[classCol]);
  const carNumIdx = findRaceNumberIndex(columnSpec);
  const carNum = carNumIdx > -1 ? `car_${car[carNumIdx]}` : null;
  const carState = car[stateCol].replace(/[\/ ]/g, "");
  return (
    <tr id={carNum} className={`car_state_${carState} car_class_${carClass} ${hasSetSB? "sb-new" : ""}`} >
      {cols}
    </tr>
  );
};

const TimingTableHeader = ({spec}) => {
  if (spec.length == 3) {
    const toolTip = <Tooltip id="timing-table-header-tooltip">{spec[2]}</Tooltip>;
    return (
      <td>
        <OverlayTrigger placement="bottom" overlay={toolTip}>
          <span className="with-tooltip">{spec[0]}</span>
        </OverlayTrigger>
      </td>);
  }
  else {
    return <td>{spec[0]}</td>;
  }
};

const TimingTable = ({cars, columnSpec}) => {
  const carRows = [];
  _(cars).forEach((car, position) => {
    carRows.push(<TimingRow car={car} key={position} position={position + 1} columnSpec={columnSpec} />);
  });
  return (
    <Table striped className="timing-table table-condensed">
      <thead>
        <tr className="timing-table-header">
          <td>Pos</td>
          {columnSpec.map((spec, idx) => <TimingTableHeader key={idx} spec={spec} />)}
        </tr>
      </thead>
      <tbody>
        {carRows}
      </tbody>
    </Table>
  );
};

export default TimingTable;
