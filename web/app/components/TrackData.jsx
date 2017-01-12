import React from 'react';

import { Grid, Row, Col } from 'react-bootstrap';

const TrackData = ({spec, dataset}) => {
  if (spec && dataset) {
    const data = [];

    for (let i = 0; i < spec.length; i++) {
      data.push(<Col sm={3} className="trackdata-key" key={spec[i]}>{spec[i]}</Col>);
      data.push(<Col sm={3} className="trackdata-value" key={spec[i] + "_value"}>{dataset[i]}</Col>);
    }

    return (
        <Grid fluid={true}>
          <Row>
            {data}
          </Row>
        </Grid>
    );
  }
  else {
    return (<p className="trackdata-key">Track data not available</p>);
  }
};

export default TrackData;
